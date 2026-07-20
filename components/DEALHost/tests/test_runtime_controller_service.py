from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest

import httpx

from dealhost.runtime_controller_service.asgi import create_application
from dealhost.runtime_controller_service.config import ControllerSettings
from dealhost.runtime_controller_service.contract import (
    ContractError,
    parse_desired_deployment,
    payload_digest,
)
from dealhost.runtime_controller_service.kubernetes import (
    MAX_KUBERNETES_RESPONSE_BYTES,
    KubernetesApiError,
    KubernetesClient,
)
from dealhost.runtime_controller_service.lease import RuntimeBusy
from dealhost.runtime_controller_service.resources import (
    COMPONENT_LABEL,
    DEPLOYMENT_LABEL,
    component_name,
    lease_name,
    state_config_map,
    state_name,
)
from dealhost.runtime_controller_service.service import (
    RuntimeConflict,
    RuntimeReconciler,
)


DEPLOYMENT_ID = "9f4d7bfe-5466-4f51-a49e-47f60bb86425"


class FakeKubernetes:
    def __init__(self, settings: ControllerSettings) -> None:
        self.settings = settings
        self.resources: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.calls: list[tuple[Any, ...]] = []
        self.log_content = "2026-01-01T00:00:00Z first\n2026-01-01T00:00:01Z second"
        self.ready_error = False
        self._lease_guard = asyncio.Lock()
        self._lease_serial = 0
        self.active_lease_holders = 0
        self.maximum_active_lease_holders = 0

    async def apply(self, resource: dict[str, Any]) -> dict[str, Any]:
        copied = deepcopy(resource)
        metadata = copied.setdefault("metadata", {})
        namespace = metadata.setdefault("namespace", self.settings.namespace)
        key = (namespace, copied["kind"], metadata["name"])
        existing = self.resources.get(key)
        if existing and copied["kind"] == "Deployment" and "status" in existing:
            copied["status"] = deepcopy(existing["status"])
        self.resources[key] = copied
        self.calls.append(("apply", namespace, copied["kind"], metadata["name"]))
        return deepcopy(copied)

    async def get(
        self,
        kind: str,
        name: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any] | None:
        resource_namespace = namespace or self.settings.namespace
        self.calls.append(("get", resource_namespace, kind, name))
        value = self.resources.get((resource_namespace, kind, name))
        return deepcopy(value) if value is not None else None

    async def list(self, kind: str, *, label_selector: str) -> list[dict[str, Any]]:
        self.calls.append(("list", self.settings.namespace, kind, label_selector))
        expected = dict(item.split("=", 1) for item in label_selector.split(","))
        result = []
        for (namespace, resource_kind, _), resource in self.resources.items():
            labels = resource.get("metadata", {}).get("labels", {})
            if (
                namespace == self.settings.namespace
                and resource_kind == kind
                and all(labels.get(key) == value for key, value in expected.items())
            ):
                result.append(deepcopy(resource))
        return result

    async def delete(self, kind: str, name: str) -> None:
        self.calls.append(("delete", self.settings.namespace, kind, name))
        self.resources.pop((self.settings.namespace, kind, name), None)

    async def create_lease(self, resource: dict[str, Any]) -> bool:
        async with self._lease_guard:
            copied = deepcopy(resource)
            metadata = copied.setdefault("metadata", {})
            namespace = metadata.setdefault("namespace", self.settings.namespace)
            key = (namespace, "Lease", metadata["name"])
            self.calls.append(("create_lease", namespace, metadata["name"]))
            if key in self.resources:
                return False
            self._lease_serial += 1
            metadata["uid"] = f"lease-{self._lease_serial}"
            metadata["resourceVersion"] = str(self._lease_serial)
            self.resources[key] = copied
            self._observe_lease_count()
            return True

    async def replace_lease(self, resource: dict[str, Any]) -> bool:
        async with self._lease_guard:
            copied = deepcopy(resource)
            metadata = copied["metadata"]
            namespace = metadata.get("namespace", self.settings.namespace)
            key = (namespace, "Lease", metadata["name"])
            self.calls.append(("replace_lease", namespace, metadata["name"]))
            existing = self.resources.get(key)
            if existing is None or existing.get("metadata", {}).get(
                "resourceVersion"
            ) != metadata.get("resourceVersion"):
                return False
            self._lease_serial += 1
            metadata["uid"] = existing["metadata"]["uid"]
            metadata["resourceVersion"] = str(self._lease_serial)
            self.resources[key] = copied
            self._observe_lease_count()
            return True

    async def release_lease(self, name: str, *, holder_identity: str) -> bool:
        async with self._lease_guard:
            key = (self.settings.namespace, "Lease", name)
            self.calls.append(("release_lease", self.settings.namespace, name))
            existing = self.resources.get(key)
            if (
                existing is None
                or existing.get("spec", {}).get("holderIdentity") != holder_identity
            ):
                return False
            self.resources.pop(key)
            self._observe_lease_count()
            return True

    def _observe_lease_count(self) -> None:
        self.active_lease_holders = sum(
            resource_kind == "Lease" for _, resource_kind, _ in self.resources
        )
        self.maximum_active_lease_holders = max(
            self.maximum_active_lease_holders,
            self.active_lease_holders,
        )

    async def pod_logs(
        self,
        pod_name: str,
        *,
        container: str,
        tail_lines: int,
        since_seconds: int,
    ) -> str:
        self.calls.append(("logs", pod_name, container, tail_lines, since_seconds))
        return self.log_content

    async def ready(self) -> None:
        self.calls.append(("ready",))
        if self.ready_error:
            raise KubernetesApiError("not ready")


def runtime_payload(
    *,
    generation: int = 1,
    desired_state: str = "running",
    autoscale: bool = False,
    with_secret: bool = False,
) -> dict[str, Any]:
    configuration_schema: dict[str, list[str]] = {"plain": ["MODE"]}
    if with_secret:
        configuration_schema["secret"] = ["API_TOKEN"]
    profile = {
        "kind": "deployment",
        "container_port": 8080,
        "healthcheck_path": "/health",
        "resources": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        },
        "configuration": configuration_schema,
        "network_egress": [],
    }
    component = {
        "module_id": 1,
        "slug": "runtime-api",
        "image": f"ghcr.io/smartappli/runtime-api@sha256:{'a' * 64}",
        "profile_schema_version": 1,
        "profile_digest": payload_digest(profile),
        "spec": profile,
    }
    manifest = {
        "schema_version": 1,
        "application": {"id": 7, "slug": "sample-runtime"},
        "version": "1.0.0",
        "version_source": "manual",
        "modules": [component],
    }
    scaling: dict[str, Any]
    if autoscale:
        scaling = {
            "runtime-api": {
                "mode": "autoscale",
                "min_replicas": 1,
                "max_replicas": 4,
                "target_cpu_utilization": 70,
            }
        }
    else:
        scaling = {"runtime-api": {"mode": "fixed", "replicas": 2}}
    return {
        "deployment_id": DEPLOYMENT_ID,
        "environment": "production",
        "generation": generation,
        "desired_state": desired_state,
        "release": {"digest": payload_digest(manifest), "manifest": manifest},
        "configuration": {"runtime-api": {"MODE": "safe"}},
        "secret_refs": (
            {"runtime-api": {"API_TOKEN": "shared-api"}}
            if with_secret
            else {"runtime-api": {}}
        ),
        "scaling": scaling,
    }


def refresh_digests(payload: dict[str, Any]) -> None:
    manifest = payload["release"]["manifest"]
    for component in manifest["modules"]:
        component["profile_digest"] = payload_digest(component["spec"])
    payload["release"]["digest"] = payload_digest(manifest)


class RuntimeControllerServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        token_file = root / "token"
        ca_file = root / "ca.crt"
        token_file.write_text("projected-kubernetes-token", encoding="utf-8")
        ca_file.write_text("test-ca", encoding="utf-8")
        self.settings = ControllerSettings(
            auth_token="controller-auth-token-with-at-least-32-chars",
            environment="production",
            namespace="archideal-runtime-apps",
            kubernetes_url="https://kubernetes.default.svc:443",
            kubernetes_token_file=token_file,
            kubernetes_ca_file=ca_file,
            allowed_image_prefixes=("ghcr.io/smartappli/",),
            workload_service_account="dealhost-runtime-application",
            image_pull_secret="archideal-registry-credentials",
            secret_name_prefix="dealapp",
            secret_catalog_name="dealhost-runtime-secret-catalog",
            secret_catalog_namespace="archideal",
        )
        self.settings.validate(require_files=True)
        self.kubernetes = FakeKubernetes(self.settings)
        self.reconciler = RuntimeReconciler(self.settings, self.kubernetes)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def desired(self, **kwargs) -> Any:
        allow_absent = kwargs.get("desired_state") == "absent"
        return parse_desired_deployment(
            runtime_payload(**kwargs),
            self.settings,
            allow_absent=allow_absent,
        )

    async def test_kubernetes_lease_client_uses_cas_and_conditional_release(
        self,
    ) -> None:
        name = lease_name(DEPLOYMENT_ID)
        holder = "holder-1"
        stored_lease = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": name,
                "namespace": self.settings.namespace,
                "uid": "lease-uid",
                "resourceVersion": "7",
            },
            "spec": {"holderIdentity": holder},
        }
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "POST":
                return httpx.Response(201, json=stored_lease)
            if request.method == "PUT":
                return httpx.Response(409, json={"kind": "Status"})
            if request.method == "GET":
                return httpx.Response(200, json=stored_lease)
            if request.method == "DELETE":
                return httpx.Response(200, json={"kind": "Status"})
            raise AssertionError(request.method)

        client = KubernetesClient(
            self.settings,
            transport=httpx.MockTransport(handler),
        )
        create_payload = deepcopy(stored_lease)
        create_payload["metadata"].pop("uid")
        create_payload["metadata"].pop("resourceVersion")
        self.assertTrue(await client.create_lease(create_payload))
        self.assertFalse(await client.replace_lease(stored_lease))
        self.assertFalse(
            await client.release_lease(name, holder_identity="another-holder")
        )
        self.assertTrue(await client.release_lease(name, holder_identity=holder))

        collection_path = (
            f"/apis/coordination.k8s.io/v1/namespaces/{self.settings.namespace}/leases"
        )
        self.assertEqual(requests[0].url.path, collection_path)
        self.assertEqual(requests[1].url.path, f"{collection_path}/{name}")
        delete_options = json.loads(requests[-1].content)
        self.assertEqual(
            delete_options["preconditions"],
            {"uid": "lease-uid", "resourceVersion": "7"},
        )
        self.assertTrue(
            all(
                request.headers["authorization"] == "Bearer projected-kubernetes-token"
                for request in requests
            )
        )

    async def test_kubernetes_lease_client_surfaces_api_errors(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"kind": "Status"})

        client = KubernetesClient(
            self.settings,
            transport=httpx.MockTransport(handler),
        )
        resource = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": lease_name(DEPLOYMENT_ID),
                "namespace": self.settings.namespace,
            },
            "spec": {"holderIdentity": "holder-1"},
        }
        with self.assertRaises(KubernetesApiError) as raised:
            await client.create_lease(resource)

        self.assertEqual(raised.exception.status_code, 403)

    async def test_kubernetes_response_limit_applies_before_decoded_buffering(
        self,
    ) -> None:
        compressed = gzip.compress(b"x" * (MAX_KUBERNETES_RESPONSE_BYTES + 1))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
                content=compressed,
            )

        client = KubernetesClient(
            self.settings,
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaisesRegex(KubernetesApiError, "too large"):
            await client.get("ConfigMap", "oversized")

    async def test_fixed_deployment_reconciles_hardened_stateless_resources(
        self,
    ) -> None:
        desired = self.desired()

        result = await self.reconciler.deploy(desired, request_id="request-0001")

        self.assertEqual(result.deployment_id, DEPLOYMENT_ID)
        self.assertEqual(result.observed_generation, 1)
        self.assertEqual(result.state, "reconciling")
        name = component_name(DEPLOYMENT_ID, "runtime-api")
        self.assertLessEqual(len(name), 63)
        deployment = self.kubernetes.resources[
            (self.settings.namespace, "Deployment", name)
        ]
        pod_spec = deployment["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        self.assertFalse(pod_spec["automountServiceAccountToken"])
        self.assertTrue(pod_spec["securityContext"]["runAsNonRoot"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertEqual(
            container["startupProbe"],
            {
                "httpGet": {
                    "path": desired.components[0].healthcheck_path,
                    "port": "http",
                },
                "periodSeconds": 5,
                "timeoutSeconds": 2,
                "failureThreshold": 30,
            },
        )
        self.assertEqual(deployment["spec"]["replicas"], 2)
        self.assertIn(
            (self.settings.namespace, "Service", name),
            self.kubernetes.resources,
        )

        deployment["metadata"]["generation"] = 3
        deployment["status"] = {
            "observedGeneration": 3,
            "readyReplicas": 2,
            "availableReplicas": 2,
        }
        self.kubernetes.resources[(self.settings.namespace, "Deployment", name)] = (
            deployment
        )
        observed = await self.reconciler.observe(DEPLOYMENT_ID)
        self.assertEqual(observed.state, "running")
        self.assertEqual(observed.components[0]["health"], "healthy")

    async def test_autoscale_restart_and_stop_are_reconciled(self) -> None:
        running = self.desired(autoscale=True)
        name = component_name(DEPLOYMENT_ID, "runtime-api")
        await self.reconciler.deploy(running, request_id="request-0002")
        self.assertIn(
            (self.settings.namespace, "HorizontalPodAutoscaler", name),
            self.kubernetes.resources,
        )

        await self.reconciler.action(
            running,
            "restart",
            request_id="restart-0001",
        )
        deployment = self.kubernetes.resources[
            (self.settings.namespace, "Deployment", name)
        ]
        self.assertEqual(
            deployment["spec"]["template"]["metadata"]["annotations"][
                "archideal.io/restart-request"
            ],
            "restart-0001",
        )

        stopped = self.desired(
            generation=2,
            desired_state="stopped",
            autoscale=True,
        )
        result = await self.reconciler.action(
            stopped,
            "stop",
            request_id="request-0003",
        )
        self.assertEqual(result.state, "stopped")
        self.assertNotIn(
            (self.settings.namespace, "HorizontalPodAutoscaler", name),
            self.kubernetes.resources,
        )
        self.assertEqual(
            self.kubernetes.resources[(self.settings.namespace, "Deployment", name)][
                "spec"
            ]["replicas"],
            0,
        )

    async def test_secret_refs_require_operator_catalog_without_reading_secrets(
        self,
    ) -> None:
        desired = self.desired(with_secret=True)
        with self.assertRaisesRegex(ContractError, "not provisioned"):
            await self.reconciler.deploy(desired, request_id="request-0004")
        self.assertFalse(any(call[0] == "apply" for call in self.kubernetes.calls))

        self.kubernetes.resources[
            ("archideal", "ConfigMap", self.settings.secret_catalog_name)
        ] = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": self.settings.secret_catalog_name,
                "namespace": "archideal",
                "labels": {
                    "app.kubernetes.io/managed-by": "archideal-operator",
                    "archideal.io/runtime-secret-catalog": "true",
                },
            },
            "immutable": True,
            "data": {
                "shared-api": json.dumps(
                    {
                        "secret_name": "dealapp-shared-api",
                        "keys": ["API_TOKEN"],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            },
        }
        self.kubernetes.calls.clear()
        await self.reconciler.deploy(desired, request_id="request-0005")
        name = component_name(DEPLOYMENT_ID, "runtime-api")
        environment = self.kubernetes.resources[
            (self.settings.namespace, "Deployment", name)
        ]["spec"]["template"]["spec"]["containers"][0]["env"]
        secret_entry = next(item for item in environment if item["name"] == "API_TOKEN")
        self.assertEqual(
            secret_entry["valueFrom"]["secretKeyRef"],
            {"name": "dealapp-shared-api", "key": "API_TOKEN"},
        )
        self.assertFalse(
            any(len(call) > 2 and call[2] == "Secret" for call in self.kubernetes.calls)
        )

    async def test_foreign_resource_blocks_all_mutation(self) -> None:
        desired = self.desired()
        name = component_name(DEPLOYMENT_ID, "runtime-api")
        self.kubernetes.resources[(self.settings.namespace, "Service", name)] = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": name,
                "namespace": self.settings.namespace,
                "labels": {"app.kubernetes.io/managed-by": "someone-else"},
            },
        }

        with self.assertRaises(RuntimeConflict):
            await self.reconciler.deploy(desired, request_id="request-0006")

        self.assertFalse(any(call[0] == "apply" for call in self.kubernetes.calls))

    async def test_generation_replay_is_idempotent_but_conflicting_reuse_fails(
        self,
    ) -> None:
        desired = self.desired()
        first = await self.reconciler.deploy(desired, request_id="request-0011")
        replay = await self.reconciler.deploy(desired, request_id="request-0012")
        self.assertEqual(replay.deployment_id, first.deployment_id)
        self.assertEqual(replay.observed_generation, first.observed_generation)

        conflicting_payload = runtime_payload()
        conflicting_payload["configuration"]["runtime-api"]["MODE"] = "changed"
        conflicting = parse_desired_deployment(conflicting_payload, self.settings)
        apply_count = sum(call[0] == "apply" for call in self.kubernetes.calls)
        with self.assertRaises(RuntimeConflict):
            await self.reconciler.deploy(conflicting, request_id="request-0013")
        self.assertEqual(
            sum(call[0] == "apply" for call in self.kubernetes.calls),
            apply_count,
        )

    async def test_expired_mutation_lease_is_taken_over(self) -> None:
        name = lease_name(DEPLOYMENT_ID)
        self.kubernetes.resources[(self.settings.namespace, "Lease", name)] = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": name,
                "namespace": self.settings.namespace,
                "uid": "abandoned-lease",
                "resourceVersion": "1",
                "labels": {
                    "app.kubernetes.io/managed-by": "dealhost-runtime-controller",
                    DEPLOYMENT_LABEL: DEPLOYMENT_ID,
                },
            },
            "spec": {
                "holderIdentity": "dead-controller",
                "leaseDurationSeconds": 10,
                "acquireTime": "2000-01-01T00:00:00.000000Z",
                "renewTime": "2000-01-01T00:00:00.000000Z",
                "leaseTransitions": 4,
            },
        }

        result = await self.reconciler.deploy(
            self.desired(),
            request_id="request-expired-lease",
        )

        self.assertEqual(result.observed_generation, 1)
        self.assertTrue(
            any(call[0] == "replace_lease" for call in self.kubernetes.calls)
        )
        self.assertNotIn(
            (self.settings.namespace, "Lease", name),
            self.kubernetes.resources,
        )

    async def test_mutation_lease_wait_is_bounded_and_retryable(self) -> None:
        name = lease_name(DEPLOYMENT_ID)
        self.kubernetes.resources[(self.settings.namespace, "Lease", name)] = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": name,
                "namespace": self.settings.namespace,
                "uid": "active-lease",
                "resourceVersion": "1",
                "labels": {
                    "app.kubernetes.io/managed-by": "dealhost-runtime-controller",
                    DEPLOYMENT_LABEL: DEPLOYMENT_ID,
                },
            },
            "spec": {
                "holderIdentity": "another-controller",
                "leaseDurationSeconds": 30,
                "acquireTime": "2999-01-01T00:00:00.000000Z",
                "renewTime": "2999-01-01T00:00:00.000000Z",
                "leaseTransitions": 0,
            },
        }
        settings = replace(self.settings, lease_acquire_timeout_seconds=0.1)
        reconciler = RuntimeReconciler(settings, self.kubernetes)

        with self.assertRaises(RuntimeBusy) as raised:
            await reconciler.deploy(
                self.desired(),
                request_id="request-contended",
            )

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.code, "runtime_busy")
        self.assertFalse(any(call[0] == "apply" for call in self.kubernetes.calls))

    async def test_undeploy_keeps_stable_result_without_retaining_a_tombstone(
        self,
    ) -> None:
        await self.reconciler.deploy(self.desired(), request_id="request-0007")
        absent = self.desired(generation=2, desired_state="absent")

        result = await self.reconciler.undeploy(
            DEPLOYMENT_ID,
            request_id="request-0008",
            desired=absent,
        )

        self.assertEqual(result.deployment_id, DEPLOYMENT_ID)
        self.assertEqual(result.observed_generation, 2)
        self.assertEqual(result.state, "deleted")
        self.assertEqual(result.components[0]["state"], "deleted")
        self.assertNotIn(
            (self.settings.namespace, "ConfigMap", state_name(DEPLOYMENT_ID)),
            self.kubernetes.resources,
        )

    async def test_concurrent_undeploys_both_return_deleted(self) -> None:
        await self.reconciler.deploy(self.desired(), request_id="request-deploy")
        absent = self.desired(generation=2, desired_state="absent")
        results = await asyncio.gather(
            self.reconciler.undeploy(
                DEPLOYMENT_ID,
                request_id="request-delete-1",
                desired=absent,
            ),
            self.reconciler.undeploy(
                DEPLOYMENT_ID,
                request_id="request-delete-2",
                desired=absent,
            ),
        )

        self.assertEqual(self.kubernetes.maximum_active_lease_holders, 1)
        self.assertEqual([result.state for result in results], ["deleted", "deleted"])
        self.assertEqual(
            [result.observed_generation for result in results],
            [2, 2],
        )
        self.assertNotIn(
            (self.settings.namespace, "ConfigMap", state_name(DEPLOYMENT_ID)),
            self.kubernetes.resources,
        )

        apply_count = sum(call[0] == "apply" for call in self.kubernetes.calls)
        replay = await self.reconciler.undeploy(
            DEPLOYMENT_ID,
            request_id="request-0008",
            desired=absent,
        )
        self.assertEqual(replay.state, "deleted")
        self.assertEqual(replay.observed_generation, 2)
        self.assertEqual(
            sum(call[0] == "apply" for call in self.kubernetes.calls),
            apply_count,
        )
        self.assertNotIn(
            (self.settings.namespace, "ConfigMap", state_name(DEPLOYMENT_ID)),
            self.kubernetes.resources,
        )

    async def test_deploy_cannot_resume_after_a_newer_undeploy(self) -> None:
        reconciler_started = asyncio.Event()
        allow_reconciler_to_continue = asyncio.Event()
        original_apply = self.kubernetes.apply
        paused = False

        async def pausing_apply(resource: dict[str, Any]) -> dict[str, Any]:
            nonlocal paused
            result = await original_apply(resource)
            if (
                not paused
                and resource.get("kind") == "ConfigMap"
                and resource.get("metadata", {}).get("name")
                == state_name(DEPLOYMENT_ID)
                and resource.get("data", {}).get("phase") == "reconciling"
            ):
                paused = True
                reconciler_started.set()
                await allow_reconciler_to_continue.wait()
            return result

        self.kubernetes.apply = pausing_apply  # type: ignore[method-assign]
        deploy_task = asyncio.create_task(
            self.reconciler.deploy(
                self.desired(),
                request_id="request-old-deploy",
            )
        )
        await asyncio.wait_for(reconciler_started.wait(), timeout=1)

        undeploy_task = asyncio.create_task(
            self.reconciler.undeploy(
                DEPLOYMENT_ID,
                request_id="request-new-delete",
                desired=self.desired(generation=2, desired_state="absent"),
            )
        )
        await asyncio.sleep(0.05)
        self.assertFalse(undeploy_task.done())

        allow_reconciler_to_continue.set()
        deploy_result, undeploy_result = await asyncio.gather(
            deploy_task,
            undeploy_task,
        )

        self.assertEqual(deploy_result.observed_generation, 1)
        self.assertEqual(undeploy_result.observed_generation, 2)
        self.assertEqual(undeploy_result.state, "deleted")
        self.assertEqual(self.kubernetes.maximum_active_lease_holders, 1)
        self.assertNotIn(
            (self.settings.namespace, "ConfigMap", state_name(DEPLOYMENT_ID)),
            self.kubernetes.resources,
        )
        self.assertNotIn(
            (
                self.settings.namespace,
                "Deployment",
                component_name(DEPLOYMENT_ID, "runtime-api"),
            ),
            self.kubernetes.resources,
        )
        self.assertNotIn(
            (self.settings.namespace, "Lease", lease_name(DEPLOYMENT_ID)),
            self.kubernetes.resources,
        )

    async def test_new_deploy_reclaims_legacy_deleted_state_configmaps(self) -> None:
        legacy = state_config_map(
            self.desired(generation=2, desired_state="absent"),
            self.settings,
            phase="deleted",
            request_id="legacy-delete",
        )
        legacy_id = "d117a390-b572-48dd-b31b-9ea20b9a4e38"
        legacy["metadata"]["name"] = state_name(legacy_id)
        legacy["metadata"]["labels"][DEPLOYMENT_LABEL] = legacy_id
        self.kubernetes.resources[
            (self.settings.namespace, "ConfigMap", state_name(legacy_id))
        ] = legacy

        await self.reconciler.deploy(self.desired(), request_id="request-legacy-gc")

        self.assertNotIn(
            (self.settings.namespace, "ConfigMap", state_name(legacy_id)),
            self.kubernetes.resources,
        )

    async def test_missing_delete_state_still_rejects_a_payload_path_mismatch(
        self,
    ) -> None:
        with self.assertRaises(ContractError):
            await self.reconciler.undeploy(
                "d117a390-b572-48dd-b31b-9ea20b9a4e38",
                request_id="request-mismatched-delete",
                desired=self.desired(generation=2, desired_state="absent"),
            )

        self.assertFalse(
            any(call[0] in {"apply", "delete"} for call in self.kubernetes.calls)
        )

    async def test_logs_are_scoped_to_component_and_window(self) -> None:
        await self.reconciler.deploy(self.desired(), request_id="request-0009")
        pod_name = "runtime-api-pod"
        self.kubernetes.resources[(self.settings.namespace, "Pod", pod_name)] = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.settings.namespace,
                "creationTimestamp": "2026-01-01T00:00:00Z",
                "resourceVersion": "42",
                "labels": {
                    "app.kubernetes.io/managed-by": "dealhost-runtime-controller",
                    DEPLOYMENT_LABEL: DEPLOYMENT_ID,
                    COMPONENT_LABEL: "runtime-api",
                },
            },
            "status": {"phase": "Running"},
        }

        result = await self.reconciler.logs(
            DEPLOYMENT_ID,
            component_slug="runtime-api",
            tail_lines=100,
            since_seconds=3600,
        )

        self.assertEqual(len(result.lines), 2)
        self.assertEqual(result.cursor, f"{pod_name}:42")
        self.assertIn(("logs", pod_name, "main", 100, 3600), self.kubernetes.calls)

    async def test_asgi_bearer_contract_and_kubernetes_readiness(self) -> None:
        app = create_application(self.settings, self.reconciler)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://controller.test",
        ) as client:
            unauthorized = await client.post("/v1/deployments", json=runtime_payload())
            self.assertEqual(unauthorized.status_code, 401)

            response = await client.post(
                "/v1/deployments",
                headers={
                    "Authorization": f"Bearer {self.settings.auth_token}",
                    "Idempotency-Key": "request-0010",
                },
                json=runtime_payload(),
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["id"], DEPLOYMENT_ID)

            ready = await client.get("/health/ready")
            self.assertEqual(ready.status_code, 200)
            metrics = await client.get("/metrics")
            self.assertEqual(metrics.status_code, 200)
            self.assertIn(
                "text/plain; version=0.0.4",
                metrics.headers["content-type"],
            )
            self.assertIn(
                "dealhost_runtime_controller_kubernetes_ready 1",
                metrics.text,
            )
            self.assertIn(
                'dealhost_runtime_controller_requests_total{method="POST",route="/v1/deployments",status="201"} 1',
                metrics.text,
            )
            self.assertNotIn(self.settings.auth_token, metrics.text)
            unknown_method = await client.request("BREW", "/unbounded-path")
            self.assertEqual(unknown_method.status_code, 401)
            bounded_metrics = await client.get("/metrics")
            self.assertIn(
                'dealhost_runtime_controller_requests_total{method="OTHER",route="unknown",status="401"} 1',
                bounded_metrics.text,
            )
            self.assertNotIn("BREW", bounded_metrics.text)
            self.kubernetes.ready_error = True
            unavailable = await client.get("/health/ready")
            self.assertEqual(unavailable.status_code, 503)
            unavailable_metrics = await client.get("/metrics")
            self.assertEqual(unavailable_metrics.status_code, 200)
            self.assertIn(
                "dealhost_runtime_controller_kubernetes_ready 0",
                unavailable_metrics.text,
            )

    async def test_network_egress_is_explicitly_rejected(self) -> None:
        payload = runtime_payload()
        payload["release"]["manifest"]["modules"][0]["spec"]["network_egress"] = [
            "database.example.com"
        ]
        refresh_digests(payload)

        with self.assertRaisesRegex(ContractError, "not enforced") as raised:
            parse_desired_deployment(payload, self.settings)

        self.assertEqual(raised.exception.code, "network_egress_unsupported")


if __name__ == "__main__":
    unittest.main()
