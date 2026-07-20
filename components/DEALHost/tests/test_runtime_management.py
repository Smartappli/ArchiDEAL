from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.hosting.models import (
    ApplicationVersion,
    HostedApplication,
    Module,
    ModuleRuntimeProfile,
    RuntimeDeployment,
    RuntimeEnvironment,
    RuntimeOperation,
)
from apps.hosting.runtime_controller import (
    RuntimeControllerError,
    RuntimeLogs,
    RuntimeSnapshot,
)
from apps.hosting.runtime_release import sha256_json
from apps.hosting.runtime_worker import RuntimeOperationProcessor
from apps.hosting.versioning import publish_immutable_version
from dealhost.settings.env import RuntimeControllerConfig


ENABLED_CONTROLLER = RuntimeControllerConfig(
    base_url="https://runtime-controller.internal",
    token="test-runtime-controller-token",
    timeout_seconds=5,
)
DISABLED_CONTROLLER = RuntimeControllerConfig(
    base_url="",
    token="",
    timeout_seconds=5,
)


class RuntimeFixtureMixin:
    def setUp(self) -> None:
        super().setUp()
        self.admin = get_user_model().objects.create_user(
            username="runtime-admin",
            password="irrelevant",  # nosec B106 - test-only fixture.
            is_staff=True,
        )
        self.client.force_authenticate(self.admin)
        self.environment = RuntimeEnvironment.objects.create(
            slug="production",
            name="Production",
            description="Isolated production namespace",
            enabled=True,
            capabilities={
                "start_stop": True,
                "restart": True,
                "scaling": {
                    "fixed": {"min_replicas": 1, "max_replicas": 10},
                    "autoscaling": {
                        "enabled": True,
                        "min_replicas": 1,
                        "max_replicas": 10,
                    },
                },
                "logs": {"max_lines": 500, "max_bytes": 262144},
                "domains": False,
            },
            policy={
                "requires_image_digest": True,
                "allowed_registries": ["ghcr.io/smartappli/"],
                "allowed_secret_refs": ["runtime-database"],
                "stateless_only": True,
            },
        )
        self.module = Module.objects.create(
            name="Runtime API",
            slug="runtime-api",
            image=f"ghcr.io/smartappli/runtime-api@sha256:{'a' * 64}",
            deployment_target=Module.DeploymentTarget.KUBERNETES,
            enabled=True,
        )
        profile_spec = {
            "kind": "deployment",
            "container_port": 8080,
            "healthcheck_path": "/health/ready",
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
            "configuration": {
                "plain": ["FEATURE_FLAG"],
                "secret": ["DATABASE_PASSWORD"],
            },
            "network_egress": [],
        }
        ModuleRuntimeProfile.objects.create(
            module=self.module,
            spec=profile_spec,
            spec_digest=sha256_json(profile_spec),
            enabled=True,
            verified_at=timezone.now(),
        )
        self.application = HostedApplication.objects.create(
            name="Runtime portal",
            slug="runtime-portal",
            current_version="1.2.3",
            enabled=True,
        )
        self.application.modules.add(self.module)
        self.version = ApplicationVersion.objects.create(
            application=self.application,
            version="1.2.3",
            source="ci",
            notes="Signed release metadata",
        )

    def deployment_payload(self) -> dict[str, object]:
        return {
            "application_id": self.application.id,
            "environment": self.environment.slug,
            "version": self.version.version,
            "configuration": {"runtime-api": {"FEATURE_FLAG": "enabled"}},
            "secret_refs": {"runtime-api": {"DATABASE_PASSWORD": "runtime-database"}},
            "scaling": {"runtime-api": {"mode": "fixed", "replicas": 2}},
        }

    def queue_deployment(self, *, key: str = "runtime-create-0001"):
        return self.client.post(
            reverse("deployments-list"),
            self.deployment_payload(),
            format="json",
            HTTP_IF_MATCH=f'"{self.application.revision}"',
            HTTP_IDEMPOTENCY_KEY=key,
        )


@override_settings(RUNTIME_CONTROLLER=ENABLED_CONTROLLER, RUNTIME_ENABLED=True)
class RuntimeManagementApiTests(RuntimeFixtureMixin, APITestCase):
    def test_lists_allowlisted_environments_and_queues_an_idempotent_deploy(
        self,
    ) -> None:
        environments = self.client.get(reverse("runtime-environments-list"))
        self.assertEqual(environments.status_code, 200)
        self.assertEqual(environments.data["results"][0]["slug"], "production")
        self.assertTrue(environments.data["results"][0]["enabled"])

        created = self.queue_deployment()
        self.assertEqual(created.status_code, 202)
        self.assertEqual(created.data["deployment"]["environment"], "production")
        self.assertEqual(created.data["deployment"]["version"], "1.2.3")
        self.assertEqual(created.data["deployment"]["desired_state"], "running")
        self.assertEqual(created.data["operation"]["type"], "deploy")
        self.assertEqual(created.data["operation"]["status"], "queued")
        self.assertEqual(
            created.data["deployment"]["components"][0]["image_digest"],
            self.module.image,
        )

        replay = self.queue_deployment()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay["Idempotent-Replay"], "true")
        self.assertEqual(
            replay.data["operation"]["id"], created.data["operation"]["id"]
        )
        self.assertEqual(RuntimeDeployment.objects.count(), 1)
        self.assertEqual(RuntimeOperation.objects.count(), 1)

    def test_rejects_stale_revisions_and_idempotency_key_reuse(self) -> None:
        stale = self.client.post(
            reverse("deployments-list"),
            self.deployment_payload(),
            format="json",
            HTTP_IF_MATCH='"99"',
            HTTP_IDEMPOTENCY_KEY="runtime-create-stale",
        )
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale.data["code"], "stale_revision")

        created = self.queue_deployment(key="runtime-shared-key")
        self.assertEqual(created.status_code, 202)
        changed_payload = self.deployment_payload()
        changed_payload["scaling"] = {"runtime-api": {"mode": "fixed", "replicas": 4}}
        conflict = self.client.post(
            reverse("deployments-list"),
            changed_payload,
            format="json",
            HTTP_IF_MATCH=f'"{self.application.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-shared-key",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "idempotency_conflict")

    def test_configuration_rejects_secret_values_and_path_like_references(self) -> None:
        payload = self.deployment_payload()
        payload["configuration"] = {
            "runtime-api": {"DATABASE_PASSWORD": "do-not-store-this"}
        }
        secret_value = self.client.post(
            reverse("deployments-list"),
            payload,
            format="json",
            HTTP_IF_MATCH=f'"{self.application.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-secret-value",
        )
        self.assertEqual(secret_value.status_code, 400)

        payload = self.deployment_payload()
        payload["secret_refs"] = {
            "runtime-api": {"DATABASE_PASSWORD": "a/../../other-secret"}
        }
        traversal = self.client.post(
            reverse("deployments-list"),
            payload,
            format="json",
            HTTP_IF_MATCH=f'"{self.application.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-secret-traversal",
        )
        self.assertEqual(traversal.status_code, 400)

        payload = self.deployment_payload()
        payload["secret_refs"] = {
            "runtime-api": {"DATABASE_PASSWORD": "unapproved-database"}
        }
        unapproved = self.client.post(
            reverse("deployments-list"),
            payload,
            format="json",
            HTTP_IF_MATCH=f'"{self.application.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-secret-unapproved",
        )
        self.assertEqual(unapproved.status_code, 400)

    def test_queues_config_actions_logs_and_soft_undeploy_with_etags(self) -> None:
        created = self.queue_deployment()
        deployment_id = created.data["deployment"]["id"]
        deployment = RuntimeDeployment.objects.get(pk=deployment_id)
        deploy_operation = deployment.operations.get()
        deploy_operation.status = RuntimeOperation.Status.SUCCEEDED
        deploy_operation.finished_at = timezone.now()
        deploy_operation.save()
        deployment.observed_state = RuntimeDeployment.ObservedState.RUNNING
        deployment.controller_id = "controller-runtime-1"
        deployment.save()

        configured = self.client.patch(
            reverse("deployments-detail", args=[deployment_id]),
            {
                "configuration": {"runtime-api": {"FEATURE_FLAG": "disabled"}},
                "secret_refs": {
                    "runtime-api": {"DATABASE_PASSWORD": "runtime-database"}
                },
                "scaling": {"runtime-api": {"mode": "fixed", "replicas": 3}},
            },
            format="json",
            HTTP_IF_MATCH='"1"',
            HTTP_IDEMPOTENCY_KEY="runtime-configure-1",
        )
        self.assertEqual(configured.status_code, 202)
        self.assertEqual(configured.data["deployment"]["revision"], 2)
        self.assertEqual(configured.data["operation"]["type"], "configure")

        configure_operation = RuntimeOperation.objects.get(
            pk=configured.data["operation"]["id"]
        )
        configure_operation.status = RuntimeOperation.Status.SUCCEEDED
        configure_operation.finished_at = timezone.now()
        configure_operation.save()
        deployment.refresh_from_db()
        deployment.observed_state = RuntimeDeployment.ObservedState.RUNNING
        deployment.save()

        stopped = self.client.post(
            reverse("deployments-actions", args=[deployment_id]),
            {"action": "stop"},
            format="json",
            HTTP_IF_MATCH='"2"',
            HTTP_IDEMPOTENCY_KEY="runtime-stop-1",
        )
        self.assertEqual(stopped.status_code, 202)
        self.assertEqual(stopped.data["deployment"]["desired_state"], "stopped")

        stop_operation = RuntimeOperation.objects.get(
            pk=stopped.data["operation"]["id"]
        )
        stop_operation.status = RuntimeOperation.Status.SUCCEEDED
        stop_operation.finished_at = timezone.now()
        stop_operation.save()
        deployment.refresh_from_db()
        deployment.observed_state = RuntimeDeployment.ObservedState.STOPPED
        deployment.controller_id = "controller-runtime-1"
        deployment.save()

        logs = self.client.post(
            reverse("deployments-log-requests", args=[deployment_id]),
            {"component": "runtime-api", "tail_lines": 100, "since_seconds": 60},
            format="json",
            HTTP_IF_MATCH='"3"',
            HTTP_IDEMPOTENCY_KEY="runtime-logs-1",
        )
        self.assertEqual(logs.status_code, 202)
        self.assertEqual(logs.data["type"], "log_snapshot")

        log_operation = RuntimeOperation.objects.get(pk=logs.data["id"])
        log_operation.status = RuntimeOperation.Status.SUCCEEDED
        log_operation.finished_at = timezone.now()
        log_operation.save()
        deployment.refresh_from_db()
        removed = self.client.delete(
            reverse("deployments-detail", args=[deployment_id]),
            HTTP_IF_MATCH=f'"{deployment.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-undeploy-1",
        )
        self.assertEqual(removed.status_code, 202)
        self.assertEqual(removed.data["deployment"]["desired_state"], "absent")
        self.assertEqual(removed.data["deployment"]["observed_state"], "deleting")

    def test_runtime_endpoints_are_staff_only(self) -> None:
        reader = get_user_model().objects.create_user(
            username="runtime-reader",
            password="irrelevant",  # nosec B106 - test-only fixture.
        )
        self.client.force_authenticate(reader)
        self.assertEqual(
            self.client.get(reverse("runtime-environments-list")).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("deployments-list")).status_code, 403)

    def test_rejects_a_version_without_a_published_runtime_contract(self) -> None:
        self.module.runtime_profile.delete()

        response = self.queue_deployment(key="runtime-missing-profile")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "release_not_deployable")
        self.assertFalse(RuntimeDeployment.objects.exists())

    def test_existing_release_remains_deployable_after_catalog_changes(self) -> None:
        first = self.queue_deployment(key="runtime-release-first")
        self.assertEqual(first.status_code, 202)
        original_image = first.data["deployment"]["components"][0]["image_digest"]
        first_deployment = RuntimeDeployment.objects.get(
            pk=first.data["deployment"]["id"]
        )
        first_deployment.deleted_at = timezone.now()
        first_deployment.save(update_fields=["deleted_at", "updated_at"])

        self.module.image = f"ghcr.io/smartappli/runtime-api@sha256:{'b' * 64}"
        self.module.slug = "renamed-api"
        self.module.save(update_fields=["image", "slug"])
        self.application.modules.clear()
        self.application.refresh_from_db()

        second = self.queue_deployment(key="runtime-release-rollback")

        self.assertEqual(second.status_code, 202)
        component = second.data["deployment"]["components"][0]
        self.assertEqual(component["slug"], "runtime-api")
        self.assertEqual(component["image_digest"], original_image)

    def test_version_publication_captures_a_digest_protected_runtime_snapshot(
        self,
    ) -> None:
        publication = publish_immutable_version(
            self.application,
            {"version": "2.0.0", "source": "ci", "notes": "runtime snapshot"},
            expected_revision=self.application.revision,
        )

        snapshot = publication.version.runtime_snapshot
        self.assertEqual(snapshot["modules"][0]["slug"], "runtime-api")
        self.assertEqual(snapshot["modules"][0]["image"], self.module.image)
        self.assertEqual(
            publication.version.runtime_snapshot_digest,
            sha256_json(snapshot),
        )

    def test_updates_use_the_immutable_release_configuration_contract(self) -> None:
        created = self.queue_deployment(key="runtime-immutable-config")
        self.assertEqual(created.status_code, 202)
        deployment = RuntimeDeployment.objects.get(pk=created.data["deployment"]["id"])
        operation = deployment.operations.get()
        operation.status = RuntimeOperation.Status.SUCCEEDED
        operation.finished_at = timezone.now()
        operation.save()
        deployment.controller_id = "controller-runtime-immutable"
        deployment.observed_state = RuntimeDeployment.ObservedState.RUNNING
        deployment.save()

        profile = self.module.runtime_profile
        changed_spec = dict(profile.spec)
        changed_spec["configuration"] = {
            "plain": ["NEW_SETTING"],
            "secret": [],
        }
        profile.spec = changed_spec
        profile.spec_digest = sha256_json(changed_spec)
        profile.save(update_fields=["spec", "spec_digest", "updated_at"])

        response = self.client.patch(
            reverse("deployments-detail", args=[deployment.id]),
            {"configuration": {"runtime-api": {"FEATURE_FLAG": "still-valid"}}},
            format="json",
            HTTP_IF_MATCH=f'"{deployment.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-immutable-update",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["operation"]["type"], "configure")

    def test_failed_deploy_without_controller_identity_can_be_retried(self) -> None:
        created = self.queue_deployment(key="runtime-first-failed")
        deployment = RuntimeDeployment.objects.get(pk=created.data["deployment"]["id"])
        operation = deployment.operations.get()
        operation.status = RuntimeOperation.Status.FAILED
        operation.finished_at = timezone.now()
        operation.save()
        deployment.observed_state = RuntimeDeployment.ObservedState.FAILED
        deployment.save()

        retried = self.client.post(
            reverse("deployments-actions", args=[deployment.id]),
            {"action": "start"},
            format="json",
            HTTP_IF_MATCH=f'"{deployment.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-retry-deploy",
        )

        self.assertEqual(retried.status_code, 202)
        self.assertEqual(retried.data["operation"]["type"], "deploy")


@override_settings(RUNTIME_CONTROLLER=DISABLED_CONTROLLER, RUNTIME_ENABLED=False)
class RuntimeUnavailableApiTests(RuntimeFixtureMixin, APITestCase):
    def test_controller_is_fail_closed_and_never_simulates_a_deploy(self) -> None:
        environments = self.client.get(reverse("runtime-environments-list"))
        self.assertFalse(environments.data["results"][0]["enabled"])

        response = self.queue_deployment()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "runtime_backend_unavailable")
        self.assertFalse(RuntimeDeployment.objects.exists())


class FakeRuntimeController:
    def __init__(self, module: Module) -> None:
        self.module = module
        self.last_log_request: dict[str, object] | None = None

    def deploy(self, payload, *, request_id: str) -> RuntimeSnapshot:
        return self.snapshot("running", payload["generation"])

    def update(self, controller_id, payload, *, request_id: str) -> RuntimeSnapshot:
        return self.snapshot("running", payload["generation"])

    def action(
        self, controller_id, action_name, payload, *, request_id: str
    ) -> RuntimeSnapshot:
        state = "stopped" if action_name == "stop" else "running"
        return self.snapshot(state, payload["generation"])

    def undeploy(self, controller_id, payload, *, request_id: str) -> RuntimeSnapshot:
        return self.snapshot("deleted", payload["generation"])

    def status(self, controller_id, *, request_id: str) -> RuntimeSnapshot:
        return self.snapshot("running", 1)

    def logs(
        self,
        controller_id,
        *,
        component: str,
        tail: int,
        since_seconds: int,
        request_id: str,
    ) -> RuntimeLogs:
        self.last_log_request = {
            "controller_id": controller_id,
            "component": component,
            "tail": tail,
            "since_seconds": since_seconds,
        }
        return RuntimeLogs(("ready", "request complete"), "cursor-1", False)

    def snapshot(self, state: str, generation: int) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            controller_id="controller-runtime-1",
            state=state,
            message="",
            observed_generation=generation,
            components=(
                {
                    "slug": self.module.slug,
                    "image_digest": self.module.image,
                    "desired_replicas": 2,
                    "ready_replicas": 2 if state == "running" else 0,
                    "available_replicas": 2 if state == "running" else 0,
                    "state": state,
                    "health": "healthy" if state == "running" else "stopped",
                    "restart_count": 0,
                    "last_error": "",
                },
            ),
        )


class StaleRuntimeController(FakeRuntimeController):
    def deploy(self, payload, *, request_id: str) -> RuntimeSnapshot:
        return self.snapshot("running", payload["generation"] - 1)


class FailingLogRuntimeController(FakeRuntimeController):
    def logs(
        self,
        controller_id,
        *,
        component: str,
        tail: int,
        since_seconds: int,
        request_id: str,
    ) -> RuntimeLogs:
        raise RuntimeControllerError("Log access was rejected.", status_code=403)


class TransientStatusRuntimeController(StaleRuntimeController):
    def status(self, controller_id, *, request_id: str) -> RuntimeSnapshot:
        raise RuntimeControllerError("Temporary controller failure.", status_code=503)


@override_settings(RUNTIME_CONTROLLER=ENABLED_CONTROLLER, RUNTIME_ENABLED=True)
class RuntimeWorkerTests(RuntimeFixtureMixin, APITestCase):
    def test_worker_reconciles_deploy_and_keeps_logs_only_in_ttl_cache(self) -> None:
        created = self.queue_deployment()
        self.assertEqual(created.status_code, 202)
        operation_id = created.data["operation"]["id"]
        processor = RuntimeOperationProcessor(
            worker_id="test-worker",
            controller=FakeRuntimeController(self.module),
        )
        self.assertTrue(processor.process_next())

        operation = RuntimeOperation.objects.get(pk=operation_id)
        deployment = operation.deployment
        deployment.refresh_from_db()
        self.assertEqual(operation.status, RuntimeOperation.Status.SUCCEEDED)
        self.assertEqual(
            deployment.observed_state, RuntimeDeployment.ObservedState.RUNNING
        )
        self.assertEqual(deployment.controller_id, "controller-runtime-1")
        self.assertEqual(deployment.components.get().ready_replicas, 2)

        logs = self.client.post(
            reverse("deployments-log-requests", args=[deployment.id]),
            {"component": "runtime-api", "tail_lines": 2, "since_seconds": 60},
            format="json",
            HTTP_IF_MATCH=f'"{deployment.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-worker-logs",
        )
        self.assertEqual(logs.status_code, 202)
        self.assertTrue(processor.process_next())
        log_operation = RuntimeOperation.objects.get(pk=logs.data["id"])
        self.assertEqual(log_operation.status, RuntimeOperation.Status.SUCCEEDED)
        self.assertNotIn("ready", str(log_operation.result))
        cached = cache.get(f"dealhost:runtime-log:{log_operation.id}")
        self.assertEqual(cached["content"], "ready\nrequest complete")
        self.assertEqual(
            processor.controller.last_log_request,
            {
                "controller_id": "controller-runtime-1",
                "component": "runtime-api",
                "tail": 2,
                "since_seconds": 60,
            },
        )

        detail = self.client.get(reverse("operations-detail", args=[log_operation.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["result"]["content"], "ready\nrequest complete")
        self.assertEqual(detail["Cache-Control"], "private, no-store")

    def test_worker_does_not_complete_on_a_stale_observed_generation(self) -> None:
        created = self.queue_deployment(key="runtime-stale-generation")
        processor = RuntimeOperationProcessor(
            worker_id="stale-worker",
            controller=StaleRuntimeController(self.module),
        )

        self.assertTrue(processor.process_next())

        operation = RuntimeOperation.objects.get(pk=created.data["operation"]["id"])
        self.assertEqual(operation.status, RuntimeOperation.Status.RUNNING)
        self.assertEqual(operation.result, {"dispatched": True})
        self.assertEqual(operation.progress["stage"], "waiting_for_generation")
        self.assertIsNotNone(operation.next_attempt_at)

    def test_status_polling_does_not_consume_controller_failure_retries(self) -> None:
        created = self.queue_deployment(key="runtime-poll-retry-budget")
        processor = RuntimeOperationProcessor(
            worker_id="retry-worker",
            controller=TransientStatusRuntimeController(self.module),
        )
        self.assertTrue(processor.process_next())
        operation = RuntimeOperation.objects.get(pk=created.data["operation"]["id"])
        operation.next_attempt_at = timezone.now()
        operation.save(update_fields=["next_attempt_at"])

        self.assertTrue(processor.process_next())

        operation.refresh_from_db()
        self.assertEqual(operation.attempts, 2)
        self.assertEqual(operation.controller_failures, 1)
        self.assertEqual(operation.status, RuntimeOperation.Status.QUEUED)

    def test_log_failure_does_not_mark_a_healthy_deployment_failed(self) -> None:
        created = self.queue_deployment(key="runtime-log-failure-deploy")
        processor = RuntimeOperationProcessor(
            worker_id="log-worker",
            controller=FailingLogRuntimeController(self.module),
        )
        self.assertTrue(processor.process_next())
        deployment = RuntimeDeployment.objects.get(pk=created.data["deployment"]["id"])
        revision_before_logs = deployment.revision

        response = self.client.post(
            reverse("deployments-log-requests", args=[deployment.id]),
            {"component": "runtime-api", "tail_lines": 10, "since_seconds": 60},
            format="json",
            HTTP_IF_MATCH=f'"{deployment.revision}"',
            HTTP_IDEMPOTENCY_KEY="runtime-log-failure",
        )
        self.assertEqual(response.status_code, 202)
        self.assertTrue(processor.process_next())

        log_operation = RuntimeOperation.objects.get(pk=response.data["id"])
        deployment.refresh_from_db()
        self.assertEqual(log_operation.status, RuntimeOperation.Status.FAILED)
        self.assertEqual(
            deployment.observed_state, RuntimeDeployment.ObservedState.RUNNING
        )
        self.assertEqual(deployment.revision, revision_before_logs)

    def test_worker_rejects_an_operation_for_an_obsolete_target_generation(
        self,
    ) -> None:
        created = self.queue_deployment(key="runtime-obsolete-operation")
        deployment = RuntimeDeployment.objects.get(pk=created.data["deployment"]["id"])
        deployment.generation += 1
        deployment.save(update_fields=["generation", "updated_at"])
        processor = RuntimeOperationProcessor(
            worker_id="generation-worker",
            controller=FakeRuntimeController(self.module),
        )

        self.assertTrue(processor.process_next())

        operation = RuntimeOperation.objects.get(pk=created.data["operation"]["id"])
        deployment.refresh_from_db()
        self.assertEqual(operation.status, RuntimeOperation.Status.FAILED)
        self.assertEqual(operation.error["code"], "runtime_controller_error")
        self.assertEqual(
            deployment.observed_state, RuntimeDeployment.ObservedState.FAILED
        )
