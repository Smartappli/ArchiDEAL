from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .config import ControllerSettings
from .contract import (
    ContractError,
    DesiredDeployment,
    parse_desired_deployment,
    payload_digest,
)
from .kubernetes import KubernetesClient
from .resources import (
    COMPONENT_LABEL,
    component_config_map,
    component_name,
    deployment_resource,
    hpa_resource,
    selector,
    service_resource,
    state_config_map,
    state_name,
)


@dataclass(frozen=True)
class RuntimeResult:
    deployment_id: str
    state: str
    message: str
    observed_generation: int
    components: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.deployment_id,
            "state": self.state,
            "message": self.message,
            "observed_generation": self.observed_generation,
            "components": list(self.components),
        }


@dataclass(frozen=True)
class LogResult:
    lines: tuple[str, ...]
    cursor: str
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "lines": list(self.lines),
            "cursor": self.cursor,
            "truncated": self.truncated,
        }


class RuntimeNotFound(ContractError):
    def __init__(self) -> None:
        super().__init__(
            "The runtime deployment does not exist.",
            code="runtime_not_found",
            status_code=404,
        )


class RuntimeConflict(ContractError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="runtime_conflict", status_code=409)


class RuntimeReconciler:
    def __init__(
        self,
        settings: ControllerSettings,
        kubernetes: KubernetesClient,
    ) -> None:
        self.settings = settings
        self.kubernetes = kubernetes

    async def deploy(
        self,
        desired: DesiredDeployment,
        *,
        request_id: str,
        require_existing: bool = False,
        restart_request: str = "",
    ) -> RuntimeResult:
        current = await self._state(desired.deployment_id)
        if require_existing and current is None:
            raise RuntimeNotFound()
        if current is not None:
            current_desired = self._desired_from_state(current)
            phase = self._phase(current)
            if phase in {"deleting", "deleted"}:
                raise RuntimeConflict("A deleted runtime identifier cannot be reused.")
            if desired.generation < current_desired.generation:
                raise RuntimeConflict("The requested runtime generation is stale.")
            if (
                desired.generation == current_desired.generation
                and payload_digest(desired.normalized_payload)
                != payload_digest(current_desired.normalized_payload)
            ):
                raise RuntimeConflict(
                    "The runtime generation was already used for another desired state."
                )

        await self.kubernetes.apply(
            state_config_map(
                desired,
                self.settings,
                phase="reconciling",
                request_id=request_id,
            )
        )
        for component in desired.components:
            name = component_name(desired.deployment_id, component.slug)
            if desired.desired_state == "stopped" or component.scaling["mode"] == "fixed":
                await self.kubernetes.delete("HorizontalPodAutoscaler", name)
            await self.kubernetes.apply(
                component_config_map(desired, component, self.settings)
            )
            await self.kubernetes.apply(
                deployment_resource(
                    desired,
                    component,
                    self.settings,
                    restart_request=restart_request,
                )
            )
            await self.kubernetes.apply(
                service_resource(desired, component, self.settings)
            )
            if (
                desired.desired_state == "running"
                and component.scaling["mode"] == "autoscale"
            ):
                await self.kubernetes.apply(
                    hpa_resource(desired, component, self.settings)
                )

        await self.kubernetes.apply(
            state_config_map(
                desired,
                self.settings,
                phase=("active" if desired.desired_state == "running" else "stopped"),
                request_id=request_id,
            )
        )
        return await self.observe(desired.deployment_id)

    async def action(
        self,
        desired: DesiredDeployment,
        action: str,
        *,
        request_id: str,
    ) -> RuntimeResult:
        if action == "start" and desired.desired_state != "running":
            raise ContractError("Start requires running desired state.")
        if action == "stop" and desired.desired_state != "stopped":
            raise ContractError("Stop requires stopped desired state.")
        if action in {"restart", "redeploy"} and desired.desired_state != "running":
            raise ContractError(f"{action.title()} requires running desired state.")
        if action not in {"start", "stop", "restart", "redeploy"}:
            raise ContractError("The runtime action is unsupported.", status_code=404)
        return await self.deploy(
            desired,
            request_id=request_id,
            require_existing=True,
            restart_request=(
                request_id if action in {"restart", "redeploy"} else ""
            ),
        )

    async def undeploy(
        self,
        deployment_id: str,
        *,
        request_id: str,
        desired: DesiredDeployment | None,
    ) -> RuntimeResult:
        current = await self._state(deployment_id)
        if current is None:
            if desired is None:
                return RuntimeResult(deployment_id, "deleted", "", 0, ())
            await self.kubernetes.apply(
                state_config_map(
                    desired,
                    self.settings,
                    phase="deleted",
                    request_id=request_id,
                )
            )
            return self._deleted_result(desired)

        current_desired = self._desired_from_state(current)
        if desired is not None:
            if desired.deployment_id != deployment_id:
                raise ContractError("DELETE payload identifier does not match its path.")
            if desired.generation < current_desired.generation:
                raise RuntimeConflict("The requested runtime generation is stale.")
            current_desired = desired
        if self._phase(current) == "deleted":
            return self._deleted_result(current_desired)

        await self.kubernetes.apply(
            state_config_map(
                current_desired,
                self.settings,
                phase="deleting",
                request_id=request_id,
            )
        )
        for component in current_desired.components:
            name = component_name(deployment_id, component.slug)
            await self.kubernetes.delete("HorizontalPodAutoscaler", name)
            await self.kubernetes.delete("Deployment", name)
            await self.kubernetes.delete("Service", name)
            await self.kubernetes.delete(
                "ConfigMap",
                component_name(deployment_id, component.slug, suffix="-cfg"),
            )
        return await self.observe(deployment_id)

    async def observe(self, deployment_id: str) -> RuntimeResult:
        state = await self._state(deployment_id)
        if state is None:
            raise RuntimeNotFound()
        desired = self._desired_from_state(state)
        phase = self._phase(state)
        if phase == "deleted":
            return self._deleted_result(desired)
        if phase == "deleting":
            remaining = False
            for component in desired.components:
                name = component_name(deployment_id, component.slug)
                for kind, resource_name in (
                    ("Deployment", name),
                    ("Service", name),
                    (
                        "ConfigMap",
                        component_name(deployment_id, component.slug, suffix="-cfg"),
                    ),
                    ("HorizontalPodAutoscaler", name),
                ):
                    if await self.kubernetes.get(kind, resource_name) is not None:
                        remaining = True
            if remaining:
                return RuntimeResult(
                    deployment_id,
                    "deleting",
                    "Runtime resources are terminating.",
                    desired.generation,
                    tuple(self._deleting_component(component) for component in desired.components),
                )
            await self.kubernetes.apply(
                state_config_map(
                    desired,
                    self.settings,
                    phase="deleted",
                    request_id=self._last_request_id(state),
                )
            )
            return self._deleted_result(desired)

        pods = await self.kubernetes.list(
            "Pod", label_selector=selector(deployment_id)
        )
        pods_by_component: dict[str, list[dict[str, Any]]] = {}
        for pod in pods:
            labels = pod.get("metadata", {}).get("labels", {})
            component = labels.get(COMPONENT_LABEL) if isinstance(labels, dict) else None
            if isinstance(component, str):
                pods_by_component.setdefault(component, []).append(pod)

        observed: list[dict[str, Any]] = []
        for component in desired.components:
            deployment = await self.kubernetes.get(
                "Deployment", component_name(deployment_id, component.slug)
            )
            observed.append(
                self._component_status(
                    desired,
                    component,
                    deployment,
                    pods_by_component.get(component.slug, []),
                )
            )

        states = {component["state"] for component in observed}
        if desired.desired_state == "stopped":
            state_value = "stopped" if states == {"stopped"} else "reconciling"
        elif "degraded" in states:
            state_value = "degraded"
        elif states == {"running"}:
            state_value = "running"
        else:
            state_value = "reconciling"
        message = next(
            (
                component["last_error"]
                for component in observed
                if component.get("last_error")
            ),
            "",
        )
        return RuntimeResult(
            deployment_id,
            state_value,
            message,
            desired.generation,
            tuple(observed),
        )

    async def logs(
        self,
        deployment_id: str,
        *,
        component_slug: str,
        tail_lines: int,
        since_seconds: int,
    ) -> LogResult:
        state = await self._state(deployment_id)
        if state is None or self._phase(state) in {"deleting", "deleted"}:
            raise RuntimeNotFound()
        desired = self._desired_from_state(state)
        if component_slug not in {item.slug for item in desired.components}:
            raise ContractError(
                "The requested component is outside the runtime release.",
                code="component_not_found",
                status_code=404,
            )
        pods = await self.kubernetes.list(
            "Pod",
            label_selector=selector(deployment_id, component_slug),
        )
        candidates = [pod for pod in pods if self._pod_phase(pod) in {"Running", "Succeeded"}]
        if not candidates:
            raise ContractError(
                "No runtime pod is available for logs.",
                code="logs_unavailable",
                status_code=409,
            )
        candidates.sort(
            key=lambda pod: str(pod.get("metadata", {}).get("creationTimestamp", "")),
            reverse=True,
        )
        pod = candidates[0]
        pod_name = pod.get("metadata", {}).get("name")
        if not isinstance(pod_name, str) or not pod_name:
            raise RuntimeConflict("Kubernetes returned an invalid runtime pod.")
        content = await self.kubernetes.pod_logs(
            pod_name,
            container="main",
            tail_lines=tail_lines,
            since_seconds=since_seconds,
        )
        lines = tuple(content.splitlines())
        truncated = len(lines) > tail_lines
        if truncated:
            lines = lines[-tail_lines:]
        resource_version = pod.get("metadata", {}).get("resourceVersion", "")
        cursor = f"{pod_name}:{resource_version}"[:500]
        return LogResult(lines, cursor, truncated)

    async def _state(self, deployment_id: str) -> dict[str, Any] | None:
        state = await self.kubernetes.get("ConfigMap", state_name(deployment_id))
        if state is None:
            return None
        labels = state.get("metadata", {}).get("labels", {})
        if not isinstance(labels, dict) or labels.get(
            "archideal.io/runtime-deployment"
        ) != deployment_id:
            raise RuntimeConflict("The runtime state object identity is invalid.")
        return state

    def _desired_from_state(self, state: dict[str, Any]) -> DesiredDeployment:
        data = state.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("desired.json"), str):
            raise RuntimeConflict("The runtime state object is corrupted.")
        try:
            payload = json.loads(data["desired.json"])
        except (TypeError, ValueError) as exc:
            raise RuntimeConflict("The runtime state object is corrupted.") from exc
        return parse_desired_deployment(payload, self.settings, allow_absent=True)

    @staticmethod
    def _phase(state: dict[str, Any]) -> str:
        data = state.get("data")
        phase = data.get("phase") if isinstance(data, dict) else None
        if phase not in {"reconciling", "active", "stopped", "deleting", "deleted"}:
            raise RuntimeConflict("The runtime state phase is invalid.")
        return phase

    @staticmethod
    def _last_request_id(state: dict[str, Any]) -> str:
        annotations = state.get("metadata", {}).get("annotations", {})
        value = annotations.get("archideal.io/last-request-id") if isinstance(annotations, dict) else ""
        return value if isinstance(value, str) and value else "controller-reconcile"

    @staticmethod
    def _pod_phase(pod: dict[str, Any]) -> str:
        status = pod.get("status")
        phase = status.get("phase") if isinstance(status, dict) else ""
        return phase if isinstance(phase, str) else ""

    @classmethod
    def _component_status(
        cls,
        desired: DesiredDeployment,
        component,
        deployment: dict[str, Any] | None,
        pods: list[dict[str, Any]],
    ) -> dict[str, Any]:
        restart_count = 0
        for pod in pods:
            status = pod.get("status")
            container_statuses = status.get("containerStatuses", []) if isinstance(status, dict) else []
            if isinstance(container_statuses, list):
                for container_status in container_statuses:
                    if isinstance(container_status, dict) and container_status.get("name") == "main":
                        value = container_status.get("restartCount", 0)
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                            restart_count += value
        if deployment is None:
            return cls._component_result(
                component,
                desired_replicas=0,
                ready=0,
                available=0,
                state="reconciling",
                health="pending",
                restart_count=restart_count,
                error="",
            )
        spec = deployment.get("spec")
        status = deployment.get("status")
        metadata = deployment.get("metadata")
        spec = spec if isinstance(spec, dict) else {}
        status = status if isinstance(status, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        desired_replicas = cls._count(spec.get("replicas", 0))
        ready = cls._count(status.get("readyReplicas", 0))
        available = cls._count(status.get("availableReplicas", 0))
        generation = cls._count(metadata.get("generation", 0))
        observed_generation = cls._count(status.get("observedGeneration", 0))
        containers = (
            spec.get("template", {}).get("spec", {}).get("containers", [])
            if isinstance(spec.get("template"), dict)
            else []
        )
        actual_image = component.image
        if isinstance(containers, list):
            main = next(
                (
                    item
                    for item in containers
                    if isinstance(item, dict) and item.get("name") == "main"
                ),
                None,
            )
            if isinstance(main, dict) and isinstance(main.get("image"), str):
                actual_image = main["image"]
        failure = cls._deployment_failure(status)
        if actual_image != component.image:
            failure = "Runtime image drift was detected."
        if desired.desired_state == "stopped":
            stopped = desired_replicas == 0 and available == 0
            state = "stopped" if stopped else "reconciling"
            health = "stopped" if stopped else "stopping"
        elif failure:
            state = "degraded"
            health = "unhealthy"
        elif (
            desired_replicas > 0
            and ready >= desired_replicas
            and available >= desired_replicas
            and observed_generation >= generation
        ):
            state = "running"
            health = "healthy"
        else:
            state = "reconciling"
            health = "progressing"
        result = cls._component_result(
            component,
            desired_replicas=desired_replicas,
            ready=ready,
            available=available,
            state=state,
            health=health,
            restart_count=restart_count,
            error=failure,
        )
        result["image_digest"] = actual_image
        return result

    @staticmethod
    def _deployment_failure(status: dict[str, Any]) -> str:
        conditions = status.get("conditions", [])
        if not isinstance(conditions, list):
            return ""
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            failed = (
                condition.get("type") == "ReplicaFailure"
                and condition.get("status") == "True"
            ) or (
                condition.get("type") == "Progressing"
                and condition.get("status") == "False"
            )
            if failed:
                message = condition.get("message") or condition.get("reason") or "Deployment reconciliation failed."
                return " ".join(str(message).split())[:500]
        return ""

    @staticmethod
    def _count(value: object) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    @staticmethod
    def _component_result(
        component,
        *,
        desired_replicas: int,
        ready: int,
        available: int,
        state: str,
        health: str,
        restart_count: int,
        error: str,
    ) -> dict[str, Any]:
        return {
            "slug": component.slug,
            "image_digest": component.image,
            "desired_replicas": min(desired_replicas, 65_535),
            "ready_replicas": min(ready, 65_535),
            "available_replicas": min(available, 65_535),
            "state": state,
            "health": health,
            "restart_count": min(restart_count, 100_000),
            "last_error": error,
        }

    @classmethod
    def _deleting_component(cls, component) -> dict[str, Any]:
        return cls._component_result(
            component,
            desired_replicas=0,
            ready=0,
            available=0,
            state="deleting",
            health="unknown",
            restart_count=0,
            error="",
        )

    @classmethod
    def _deleted_result(cls, desired: DesiredDeployment) -> RuntimeResult:
        return RuntimeResult(
            desired.deployment_id,
            "deleted",
            "",
            desired.generation,
            tuple(
                cls._component_result(
                    component,
                    desired_replicas=0,
                    ready=0,
                    available=0,
                    state="deleted",
                    health="unknown",
                    restart_count=0,
                    error="",
                )
                for component in desired.components
            ),
        )
