from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
import time
from typing import Any
import uuid

from .config import ControllerSettings
from .contract import ContractError
from .kubernetes import KubernetesApiError, KubernetesClient
from .resources import DEPLOYMENT_LABEL, MANAGED_BY, lease_name


class RuntimeBusy(ContractError):
    def __init__(self) -> None:
        super().__init__(
            "Another runtime mutation is still in progress.",
            code="runtime_busy",
            status_code=429,
        )


class DeploymentLeaseManager:
    """Serialize one deployment's mutations across controller replicas."""

    def __init__(
        self,
        settings: ControllerSettings,
        kubernetes: KubernetesClient,
    ) -> None:
        self.settings = settings
        self.kubernetes = kubernetes

    @asynccontextmanager
    async def hold(self, deployment_id: str) -> AsyncIterator[None]:
        name = lease_name(deployment_id)
        holder_identity = uuid.uuid4().hex
        await self._acquire(name, deployment_id, holder_identity)

        owner_task = asyncio.current_task()
        if owner_task is None:  # pragma: no cover - asyncio always owns this call
            raise RuntimeError("A runtime Lease requires an asyncio task.")
        lease_lost = asyncio.Event()
        renewal = asyncio.create_task(
            self._renew_until_cancelled(
                name,
                deployment_id,
                holder_identity,
                lease_lost,
                owner_task,
            )
        )
        body_failed = False
        try:
            yield
        except asyncio.CancelledError:
            body_failed = True
            if lease_lost.is_set():
                raise KubernetesApiError(
                    "The Kubernetes runtime mutation Lease was lost."
                ) from None
            raise
        except BaseException:
            body_failed = True
            raise
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            try:
                released = await asyncio.shield(
                    self.kubernetes.release_lease(
                        name,
                        holder_identity=holder_identity,
                    )
                )
                if not released and not lease_lost.is_set() and not body_failed:
                    raise KubernetesApiError(
                        "The Kubernetes runtime mutation Lease could not be released."
                    )
            except KubernetesApiError:
                # Preserve the original reconciliation failure.  An unreleased
                # Lease remains safe and becomes acquirable after its bounded TTL.
                if not body_failed:
                    raise

    async def _acquire(
        self,
        name: str,
        deployment_id: str,
        holder_identity: str,
    ) -> None:
        deadline = time.monotonic() + self.settings.lease_acquire_timeout_seconds
        while True:
            if await self._try_acquire(name, deployment_id, holder_identity):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeBusy()
            await asyncio.sleep(min(0.1, remaining))

    async def _try_acquire(
        self,
        name: str,
        deployment_id: str,
        holder_identity: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        current = await self.kubernetes.get("Lease", name)
        if current is None:
            return await self.kubernetes.create_lease(
                self._new_lease(
                    name,
                    deployment_id,
                    holder_identity,
                    now,
                )
            )

        metadata, spec = self._validated_lease(current, name, deployment_id)
        current_holder = spec.get("holderIdentity")
        if current_holder and not self._expired(spec, now):
            return False
        replacement = self._replacement_lease(
            metadata,
            spec,
            deployment_id,
            holder_identity,
            now,
            takeover=bool(current_holder),
        )
        return await self.kubernetes.replace_lease(replacement)

    async def _renew_until_cancelled(
        self,
        name: str,
        deployment_id: str,
        holder_identity: str,
        lease_lost: asyncio.Event,
        owner_task: asyncio.Task[Any],
    ) -> None:
        interval = max(1.0, self.settings.lease_duration_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            try:
                renewed = await self._renew(
                    name,
                    deployment_id,
                    holder_identity,
                )
            except KubernetesApiError:
                renewed = False
            if not renewed:
                lease_lost.set()
                owner_task.cancel()
                return

    async def _renew(
        self,
        name: str,
        deployment_id: str,
        holder_identity: str,
    ) -> bool:
        current = await self.kubernetes.get("Lease", name)
        if current is None:
            return False
        metadata, spec = self._validated_lease(current, name, deployment_id)
        if spec.get("holderIdentity") != holder_identity:
            return False
        replacement = self._replacement_lease(
            metadata,
            spec,
            deployment_id,
            holder_identity,
            datetime.now(timezone.utc),
            takeover=False,
        )
        return await self.kubernetes.replace_lease(replacement)

    def _new_lease(
        self,
        name: str,
        deployment_id: str,
        holder_identity: str,
        now: datetime,
    ) -> dict[str, Any]:
        timestamp = self._timestamp(now)
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": name,
                "namespace": self.settings.namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": MANAGED_BY,
                    DEPLOYMENT_LABEL: deployment_id,
                },
            },
            "spec": {
                "holderIdentity": holder_identity,
                "leaseDurationSeconds": self.settings.lease_duration_seconds,
                "acquireTime": timestamp,
                "renewTime": timestamp,
                "leaseTransitions": 0,
            },
        }

    def _replacement_lease(
        self,
        metadata: dict[str, Any],
        spec: dict[str, Any],
        deployment_id: str,
        holder_identity: str,
        now: datetime,
        *,
        takeover: bool,
    ) -> dict[str, Any]:
        transitions = spec.get("leaseTransitions", 0)
        if (
            not isinstance(transitions, int)
            or isinstance(transitions, bool)
            or transitions < 0
        ):
            raise KubernetesApiError("Kubernetes returned an invalid Lease transition.")
        timestamp = self._timestamp(now)
        acquire_time = timestamp if takeover else spec.get("acquireTime", timestamp)
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": metadata["name"],
                "namespace": self.settings.namespace,
                "resourceVersion": metadata["resourceVersion"],
                "labels": {
                    "app.kubernetes.io/managed-by": MANAGED_BY,
                    DEPLOYMENT_LABEL: deployment_id,
                },
            },
            "spec": {
                "holderIdentity": holder_identity,
                "leaseDurationSeconds": self.settings.lease_duration_seconds,
                "acquireTime": acquire_time,
                "renewTime": timestamp,
                "leaseTransitions": transitions + (1 if takeover else 0),
            },
        }

    def _validated_lease(
        self,
        lease: dict[str, Any],
        name: str,
        deployment_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        metadata = lease.get("metadata")
        spec = lease.get("spec")
        labels = metadata.get("labels") if isinstance(metadata, dict) else None
        if (
            lease.get("apiVersion") != "coordination.k8s.io/v1"
            or lease.get("kind") != "Lease"
            or not isinstance(metadata, dict)
            or metadata.get("name") != name
            or metadata.get("namespace") != self.settings.namespace
            or not isinstance(metadata.get("resourceVersion"), str)
            or not metadata["resourceVersion"]
            or not isinstance(labels, dict)
            or labels.get("app.kubernetes.io/managed-by") != MANAGED_BY
            or labels.get(DEPLOYMENT_LABEL) != deployment_id
            or not isinstance(spec, dict)
        ):
            raise KubernetesApiError("Kubernetes returned an invalid runtime Lease.")
        holder = spec.get("holderIdentity")
        if holder is not None and not isinstance(holder, str):
            raise KubernetesApiError("Kubernetes returned an invalid Lease holder.")
        return metadata, spec

    @staticmethod
    def _expired(spec: dict[str, Any], now: datetime) -> bool:
        duration = spec.get("leaseDurationSeconds")
        renewed_at = spec.get("renewTime") or spec.get("acquireTime")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration <= 0
            or not isinstance(renewed_at, str)
        ):
            raise KubernetesApiError("Kubernetes returned an invalid Lease lifetime.")
        try:
            parsed = datetime.fromisoformat(renewed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise KubernetesApiError(
                "Kubernetes returned an invalid Lease timestamp."
            ) from exc
        if parsed.tzinfo is None:
            raise KubernetesApiError("Kubernetes returned an invalid Lease timestamp.")
        return now >= parsed.astimezone(timezone.utc) + timedelta(seconds=duration)

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
