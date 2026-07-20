from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta
from typing import Any, Callable

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import RuntimeDeployment, RuntimeOperation
from .runtime_controller import (
    RuntimeControllerClient,
    RuntimeControllerError,
    RuntimeControllerUnavailable,
    RuntimeLogs,
    RuntimeSnapshot,
)


TRANSITIONAL_STATES = {"pending", "reconciling", "deleting"}
MAX_CONTROLLER_FAILURES = 5
MAX_RECONCILIATION_AGE = timedelta(minutes=30)
LOG_TTL_SECONDS = 300
logger = logging.getLogger(__name__)


class RuntimeOperationProcessor:
    """Lease and reconcile durable operations from a separate worker process."""

    def __init__(
        self,
        *,
        worker_id: str,
        controller: RuntimeControllerClient | None = None,
    ) -> None:
        self.worker_id = worker_id[:128]
        self.controller = controller or RuntimeControllerClient()

    def process_next(self) -> bool:
        claimed = self._claim()
        if claimed is None:
            return False
        operation_id, lease_token = claimed
        operation = (
            RuntimeOperation.objects.select_related(
                "deployment__application",
                "deployment__release__application_version",
                "deployment__environment",
            )
            .prefetch_related("deployment__components")
            .get(pk=operation_id)
        )
        try:
            self._execute(operation, lease_token)
        except (RuntimeControllerUnavailable, RuntimeControllerError) as exc:
            self._record_controller_failure(operation, lease_token, exc)
        except Exception:
            logger.exception(
                "Unexpected runtime worker failure for operation %s", operation.id
            )
            self._record_unexpected_failure(operation, lease_token)
        return True

    def run(
        self,
        *,
        once: bool = False,
        poll_seconds: float = 2.0,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        while True:
            if heartbeat is not None:
                heartbeat()
            processed = self.process_next()
            if heartbeat is not None:
                heartbeat()
            if once:
                return
            if not processed:
                time.sleep(poll_seconds)

    def _claim(self) -> tuple[uuid.UUID, uuid.UUID] | None:
        now = timezone.now()
        with transaction.atomic():
            operation = (
                RuntimeOperation.objects.select_for_update()
                .filter(
                    Q(status=RuntimeOperation.Status.QUEUED)
                    | Q(
                        status=RuntimeOperation.Status.RUNNING,
                        lease_expires_at__lte=now,
                    )
                    | Q(
                        status=RuntimeOperation.Status.RUNNING,
                        lease_expires_at__isnull=True,
                    )
                )
                .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
                .order_by("requested_at")
                .first()
            )
            if operation is None:
                return None
            lease_token = uuid.uuid4()
            operation.status = RuntimeOperation.Status.RUNNING
            operation.started_at = operation.started_at or now
            operation.attempts += 1
            operation.leased_by = self.worker_id
            operation.lease_token = lease_token
            operation.lease_expires_at = now + timedelta(seconds=90)
            operation.next_attempt_at = None
            operation.progress = {"stage": "dispatching", "percent": 10}
            operation.save()
            return operation.id, lease_token

    def _execute(self, operation: RuntimeOperation, lease_token: uuid.UUID) -> None:
        deployment = operation.deployment
        if operation.operation_type == RuntimeOperation.OperationType.LOG_SNAPSHOT:
            logs = self.controller.logs(
                deployment.controller_id,
                component=operation.payload["component"],
                tail=operation.payload["tail_lines"],
                since_seconds=operation.payload["since_seconds"],
                request_id=str(operation.id),
            )
            self._complete_logs(operation, lease_token, logs)
            return
        if deployment.generation != operation.target_generation:
            raise RuntimeControllerError(
                "The queued operation no longer matches the deployment generation.",
                status_code=409,
            )

        already_dispatched = bool(
            isinstance(operation.result, dict) and operation.result.get("dispatched")
        )
        if already_dispatched:
            try:
                snapshot = self.controller.status(
                    deployment.controller_id,
                    request_id=str(operation.id),
                )
            except RuntimeControllerError as exc:
                # A completed undeploy deliberately removes its state ConfigMap so
                # namespace quota is not consumed forever. If the terminal status
                # response was lost, retry the idempotent DELETE with the immutable
                # desired payload instead of turning the deployment into failed.
                if (
                    operation.operation_type
                    != RuntimeOperation.OperationType.UNDEPLOY
                    or exc.status_code != 404
                ):
                    raise
                snapshot = self.controller.undeploy(
                    deployment.controller_id or str(deployment.id),
                    _controller_payload(deployment, operation),
                    request_id=str(operation.id),
                )
        else:
            payload = _controller_payload(deployment, operation)
            operation_type = operation.operation_type
            if operation_type == RuntimeOperation.OperationType.DEPLOY:
                snapshot = self.controller.deploy(payload, request_id=str(operation.id))
            elif operation_type in {
                RuntimeOperation.OperationType.CONFIGURE,
                RuntimeOperation.OperationType.SCALE,
            }:
                snapshot = self.controller.update(
                    deployment.controller_id,
                    payload,
                    request_id=str(operation.id),
                )
            elif operation_type in {
                RuntimeOperation.OperationType.START,
                RuntimeOperation.OperationType.STOP,
                RuntimeOperation.OperationType.RESTART,
            }:
                snapshot = self.controller.action(
                    deployment.controller_id,
                    operation_type,
                    payload,
                    request_id=str(operation.id),
                )
            elif operation_type == RuntimeOperation.OperationType.UNDEPLOY:
                snapshot = self.controller.undeploy(
                    deployment.controller_id or str(deployment.id),
                    payload,
                    request_id=str(operation.id),
                )
            else:
                raise RuntimeControllerError("Unsupported queued runtime operation.")
        self._record_snapshot(operation, lease_token, snapshot)

    def _record_snapshot(
        self,
        operation: RuntimeOperation,
        lease_token: uuid.UUID,
        snapshot: RuntimeSnapshot,
    ) -> None:
        now = timezone.now()
        with transaction.atomic():
            locked_operation = RuntimeOperation.objects.select_for_update().get(
                pk=operation.pk
            )
            if locked_operation.lease_token != lease_token:
                return
            deployment = (
                RuntimeDeployment.objects.select_for_update()
                .select_related("release__application_version")
                .get(pk=locked_operation.deployment_id)
            )
            waiting_for_generation = (
                snapshot.observed_generation < locked_operation.target_generation
                and snapshot.state
                not in {
                    RuntimeDeployment.ObservedState.FAILED,
                    RuntimeDeployment.ObservedState.UNKNOWN,
                }
            )
            if snapshot.state in TRANSITIONAL_STATES or waiting_for_generation:
                _validate_snapshot_generation(
                    deployment,
                    snapshot,
                    target_generation=locked_operation.target_generation,
                )
                self._apply_components(deployment, snapshot, mutate=False)
                deployment.controller_id = snapshot.controller_id
                deployment.revision += 1
                deployment.last_reconciled_at = now
                deployment.save(
                    update_fields=[
                        "controller_id",
                        "revision",
                        "last_reconciled_at",
                        "updated_at",
                    ]
                )
                reconciliation_started_at = (
                    locked_operation.started_at or locked_operation.requested_at
                )
                if now - reconciliation_started_at >= MAX_RECONCILIATION_AGE:
                    detail = "Runtime reconciliation timed out."
                    deployment.observed_state = RuntimeDeployment.ObservedState.FAILED
                    deployment.last_error = detail
                    deployment.save(
                        update_fields=["observed_state", "last_error", "updated_at"]
                    )
                    locked_operation.status = RuntimeOperation.Status.FAILED
                    locked_operation.error = {
                        "code": "runtime_reconciliation_timeout",
                        "detail": detail,
                        "retryable": True,
                    }
                    locked_operation.progress = {"stage": "failed", "percent": 100}
                    locked_operation.finished_at = now
                    locked_operation.next_attempt_at = None
                    locked_operation.leased_by = ""
                    locked_operation.lease_token = None
                    locked_operation.lease_expires_at = None
                    locked_operation.save()
                    return
                locked_operation.status = RuntimeOperation.Status.RUNNING
                locked_operation.result = {"dispatched": True}
                locked_operation.progress = {
                    "stage": (
                        snapshot.state
                        if not waiting_for_generation
                        else "waiting_for_generation"
                    ),
                    "percent": 50,
                }
                locked_operation.next_attempt_at = now + timedelta(seconds=2)
                locked_operation.leased_by = ""
                locked_operation.lease_token = None
                locked_operation.lease_expires_at = None
                locked_operation.save()
                return

            _apply_snapshot(
                deployment,
                snapshot,
                target_generation=locked_operation.target_generation,
            )
            deployment.revision += 1
            deployment.last_reconciled_at = now
            deployment.save()
            self._apply_components(deployment, snapshot)

            terminal_error = _terminal_state_error(operation, deployment, snapshot)
            if (
                snapshot.state
                in {
                    RuntimeDeployment.ObservedState.FAILED,
                    RuntimeDeployment.ObservedState.UNKNOWN,
                }
                or terminal_error
            ):
                locked_operation.status = RuntimeOperation.Status.FAILED
                locked_operation.error = {
                    "code": "runtime_reconciliation_failed",
                    "detail": terminal_error
                    or snapshot.message
                    or "Runtime reconciliation failed.",
                    "retryable": True,
                }
                if terminal_error:
                    deployment.observed_state = RuntimeDeployment.ObservedState.FAILED
                    deployment.last_error = terminal_error
                    deployment.save(
                        update_fields=["observed_state", "last_error", "updated_at"]
                    )
            else:
                locked_operation.status = RuntimeOperation.Status.SUCCEEDED
                locked_operation.result = {
                    "state": snapshot.state,
                    "observed_generation": snapshot.observed_generation,
                }
                locked_operation.error = None
            locked_operation.progress = {"stage": snapshot.state, "percent": 100}
            locked_operation.finished_at = now
            locked_operation.next_attempt_at = None
            locked_operation.leased_by = ""
            locked_operation.lease_token = None
            locked_operation.lease_expires_at = None
            locked_operation.save()

    def _apply_components(
        self,
        deployment: RuntimeDeployment,
        snapshot: RuntimeSnapshot,
        *,
        mutate: bool = True,
    ) -> None:
        components = {
            component.slug: component for component in deployment.components.all()
        }
        expected = set(components)
        received = {component["slug"] for component in snapshot.components}
        if snapshot.state == RuntimeDeployment.ObservedState.DELETED and not received:
            if not mutate:
                return
            for component in components.values():
                component.desired_replicas = 0
                component.ready_replicas = 0
                component.available_replicas = 0
                component.state = RuntimeDeployment.ObservedState.DELETED
                component.health = "stopped"
                component.last_error = ""
                component.save()
            return
        if received != expected:
            raise RuntimeControllerError(
                "Runtime controller component set does not match the immutable release."
            )
        for observed in snapshot.components:
            component = components[observed["slug"]]
            if observed["image_digest"] != component.image_digest:
                raise RuntimeControllerError(
                    "Runtime controller reported an image outside the immutable release."
                )
            if not mutate:
                continue
            for field in (
                "desired_replicas",
                "ready_replicas",
                "available_replicas",
                "state",
                "health",
                "restart_count",
                "last_error",
            ):
                setattr(component, field, observed[field])
            component.save()

    def _complete_logs(
        self,
        operation: RuntimeOperation,
        lease_token: uuid.UUID,
        logs: RuntimeLogs,
    ) -> None:
        now = timezone.now()
        maximum_bytes = 262_144
        capabilities = operation.deployment.environment.capabilities
        if isinstance(capabilities, dict) and isinstance(
            capabilities.get("logs"), dict
        ):
            configured = capabilities["logs"].get("max_bytes", maximum_bytes)
            if isinstance(configured, int) and not isinstance(configured, bool):
                maximum_bytes = min(max(configured, 1), 262_144)
        content = "\n".join(logs.lines)
        encoded = content.encode("utf-8")
        truncated = logs.truncated or len(encoded) > maximum_bytes
        if len(encoded) > maximum_bytes:
            content = encoded[:maximum_bytes].decode("utf-8", errors="ignore")
        snapshot = {
            "component": operation.payload["component"],
            "container": "main",
            "content": content,
            "truncated": truncated,
            "line_count": len(content.splitlines()),
            "captured_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=LOG_TTL_SECONDS)).isoformat(),
        }
        cache.set(
            f"dealhost:runtime-log:{operation.id}",
            snapshot,
            timeout=LOG_TTL_SECONDS,
        )
        with transaction.atomic():
            locked = RuntimeOperation.objects.select_for_update().get(pk=operation.pk)
            if locked.lease_token != lease_token:
                cache.delete(f"dealhost:runtime-log:{operation.id}")
                return
            locked.status = RuntimeOperation.Status.SUCCEEDED
            locked.progress = {"stage": "captured", "percent": 100}
            locked.result = {"ephemeral": True, "expires_at": snapshot["expires_at"]}
            locked.error = None
            locked.finished_at = now
            locked.leased_by = ""
            locked.lease_token = None
            locked.lease_expires_at = None
            locked.save()

    def _record_controller_failure(
        self,
        operation: RuntimeOperation,
        lease_token: uuid.UUID,
        exc: RuntimeControllerError | RuntimeControllerUnavailable,
    ) -> None:
        retryable = not (
            isinstance(exc, RuntimeControllerError)
            and exc.status_code is not None
            and 400 <= exc.status_code < 500
            and exc.status_code not in {408, 429}
        )
        with transaction.atomic():
            locked = RuntimeOperation.objects.select_for_update().get(pk=operation.pk)
            if locked.lease_token != lease_token:
                return
            locked.controller_failures += 1
            if retryable and locked.controller_failures < MAX_CONTROLLER_FAILURES:
                locked.status = RuntimeOperation.Status.QUEUED
                locked.progress = {"stage": "retrying", "percent": None}
                locked.next_attempt_at = timezone.now() + timedelta(
                    seconds=min(2**locked.attempts, 60)
                )
                locked.leased_by = ""
                locked.lease_token = None
                locked.lease_expires_at = None
                locked.save()
                return
            locked.status = RuntimeOperation.Status.FAILED
            locked.error = {
                "code": "runtime_controller_error",
                "detail": str(exc)[:500],
                "retryable": retryable,
            }
            locked.progress = {"stage": "failed", "percent": 100}
            locked.finished_at = timezone.now()
            locked.leased_by = ""
            locked.lease_token = None
            locked.lease_expires_at = None
            locked.save()
            if locked.operation_type != RuntimeOperation.OperationType.LOG_SNAPSHOT:
                deployment = RuntimeDeployment.objects.select_for_update().get(
                    pk=locked.deployment_id
                )
                deployment.observed_state = RuntimeDeployment.ObservedState.FAILED
                deployment.last_error = str(exc)[:500]
                deployment.revision += 1
                deployment.save()

    def _record_unexpected_failure(
        self,
        operation: RuntimeOperation,
        lease_token: uuid.UUID,
    ) -> None:
        with transaction.atomic():
            locked = RuntimeOperation.objects.select_for_update().get(pk=operation.pk)
            if locked.lease_token != lease_token:
                return
            locked.status = RuntimeOperation.Status.FAILED
            locked.error = {
                "code": "runtime_worker_error",
                "detail": "The runtime worker failed unexpectedly.",
                "retryable": True,
            }
            locked.progress = {"stage": "failed", "percent": 100}
            locked.finished_at = timezone.now()
            locked.leased_by = ""
            locked.lease_token = None
            locked.lease_expires_at = None
            locked.save()
            if locked.operation_type != RuntimeOperation.OperationType.LOG_SNAPSHOT:
                deployment = RuntimeDeployment.objects.select_for_update().get(
                    pk=locked.deployment_id
                )
                deployment.observed_state = RuntimeDeployment.ObservedState.FAILED
                deployment.last_error = "The runtime worker failed unexpectedly."
                deployment.revision += 1
                deployment.save()


def _controller_payload(
    deployment: RuntimeDeployment,
    operation: RuntimeOperation,
) -> dict[str, Any]:
    return {
        "deployment_id": str(deployment.id),
        "environment": deployment.environment_id,
        "generation": operation.target_generation,
        "desired_state": operation.payload.get(
            "desired_state", deployment.desired_state
        ),
        "release": {
            "digest": deployment.release.manifest_digest,
            "manifest": deployment.release.manifest,
        },
        "configuration": deployment.configuration,
        "secret_refs": deployment.secret_refs,
        "scaling": deployment.scaling,
    }


def _apply_snapshot(
    deployment: RuntimeDeployment,
    snapshot: RuntimeSnapshot,
    *,
    target_generation: int,
) -> None:
    _validate_snapshot_generation(
        deployment,
        snapshot,
        target_generation=target_generation,
    )
    deployment.controller_id = snapshot.controller_id
    deployment.observed_state = snapshot.state
    deployment.observed_generation = snapshot.observed_generation
    deployment.last_error = (
        snapshot.message if snapshot.state in {"degraded", "failed", "unknown"} else ""
    )
    if snapshot.state == RuntimeDeployment.ObservedState.DELETED:
        deployment.deleted_at = timezone.now()


def _validate_snapshot_generation(
    deployment: RuntimeDeployment,
    snapshot: RuntimeSnapshot,
    *,
    target_generation: int,
) -> None:
    if snapshot.observed_generation > target_generation:
        raise RuntimeControllerError(
            "Runtime controller reported a generation newer than the queued operation."
        )
    if snapshot.observed_generation < deployment.observed_generation:
        raise RuntimeControllerError(
            "Runtime controller reported an observed generation older than DEALHost state."
        )


def _terminal_state_error(
    operation: RuntimeOperation,
    deployment: RuntimeDeployment,
    snapshot: RuntimeSnapshot,
) -> str:
    if snapshot.state in {
        RuntimeDeployment.ObservedState.FAILED,
        RuntimeDeployment.ObservedState.UNKNOWN,
    }:
        return ""
    if operation.operation_type == RuntimeOperation.OperationType.UNDEPLOY:
        expected = {RuntimeDeployment.ObservedState.DELETED}
    desired_state = operation.payload.get("desired_state", deployment.desired_state)
    if desired_state == RuntimeDeployment.DesiredState.RUNNING:
        expected = {
            RuntimeDeployment.ObservedState.RUNNING,
            RuntimeDeployment.ObservedState.DEGRADED,
        }
    elif desired_state == RuntimeDeployment.DesiredState.STOPPED:
        expected = {RuntimeDeployment.ObservedState.STOPPED}
    else:
        expected = {RuntimeDeployment.ObservedState.DELETED}
    if snapshot.state in expected:
        return ""
    return (
        f"Runtime controller reported terminal state {snapshot.state} while "
        f"the desired state is {desired_state}."
    )
