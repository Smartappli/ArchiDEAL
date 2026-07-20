from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import threading
import time
from typing import Callable

from django.db import close_old_connections
from django.db.models import Count, Min, Q, Sum
from django.utils import timezone

from .models import RuntimeDeployment, RuntimeOperation


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeWorkerSnapshot:
    operation_counts: tuple[tuple[str, str, int], ...]
    queue_depths: dict[str, int]
    oldest_ages: dict[str, float]
    stale_leases: int
    active_controller_failures: int
    deployment_counts: tuple[tuple[str, int], ...]


class RuntimeWorkerHealth:
    """Process-local heartbeat used to detect a wedged worker loop."""

    def __init__(
        self,
        *,
        heartbeat_timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if not 5 <= heartbeat_timeout_seconds <= 600:
            raise ValueError("heartbeat timeout must be between 5 and 600 seconds")
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._clock = clock
        self.started_at = wall_clock()
        self._last_heartbeat = clock()
        self._lock = threading.Lock()

    def beat(self) -> None:
        with self._lock:
            self._last_heartbeat = self._clock()

    def heartbeat_age_seconds(self) -> float:
        with self._lock:
            age = self._clock() - self._last_heartbeat
        return max(age, 0.0)

    def is_fresh(self) -> bool:
        return self.heartbeat_age_seconds() <= self.heartbeat_timeout_seconds

    def is_live(self) -> bool:
        return self.heartbeat_age_seconds() <= self.heartbeat_timeout_seconds * 2


def collect_runtime_worker_snapshot(
    *, now: datetime | None = None
) -> RuntimeWorkerSnapshot:
    now = now or timezone.now()
    close_old_connections()
    try:
        rows = list(
            RuntimeOperation.objects.filter(
                status__in=(
                    RuntimeOperation.Status.QUEUED,
                    RuntimeOperation.Status.RUNNING,
                )
            )
            .values("status", "operation_type")
            .annotate(
                total=Count("id"),
                oldest=Min("requested_at"),
                controller_failure_count=Sum("controller_failures"),
            )
            .order_by("status", "operation_type")
        )
        deployment_rows = list(
            RuntimeDeployment.objects.values("observed_state")
            .annotate(total=Count("id"))
            .order_by("observed_state")
        )
        stale_leases = RuntimeOperation.objects.filter(
            Q(lease_expires_at__lte=now)
            | (
                Q(lease_expires_at__isnull=True)
                & (Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            ),
            status=RuntimeOperation.Status.RUNNING,
        ).count()
    finally:
        close_old_connections()

    queue_depths = {
        RuntimeOperation.Status.QUEUED: 0,
        RuntimeOperation.Status.RUNNING: 0,
    }
    oldest_ages = {
        RuntimeOperation.Status.QUEUED: 0.0,
        RuntimeOperation.Status.RUNNING: 0.0,
    }
    operation_counts: dict[tuple[str, str], int] = {}
    active_controller_failures = 0
    for row in rows:
        status = str(row["status"])
        total = int(row["total"])
        operation_type = str(row["operation_type"])
        if operation_type not in RuntimeOperation.OperationType.values:
            operation_type = "unknown"
        operation_key = (status, operation_type)
        operation_counts[operation_key] = operation_counts.get(operation_key, 0) + total
        queue_depths[status] = queue_depths.get(status, 0) + total
        if status in oldest_ages and row["oldest"] is not None:
            age = max((now - row["oldest"]).total_seconds(), 0.0)
            oldest_ages[status] = max(oldest_ages[status], age)
        if status in {
            RuntimeOperation.Status.QUEUED,
            RuntimeOperation.Status.RUNNING,
        }:
            active_controller_failures += int(row["controller_failure_count"] or 0)

    deployment_counts: dict[str, int] = {}
    for row in deployment_rows:
        state = str(row["observed_state"])
        if state not in RuntimeDeployment.ObservedState.values:
            state = "unknown"
        deployment_counts[state] = deployment_counts.get(state, 0) + int(row["total"])

    return RuntimeWorkerSnapshot(
        operation_counts=tuple(
            (status, operation_type, total)
            for (status, operation_type), total in sorted(operation_counts.items())
        ),
        queue_depths=queue_depths,
        oldest_ages=oldest_ages,
        stale_leases=stale_leases,
        active_controller_failures=active_controller_failures,
        deployment_counts=tuple(sorted(deployment_counts.items())),
    )


def render_runtime_worker_metrics(
    health: RuntimeWorkerHealth,
    snapshot: RuntimeWorkerSnapshot | None,
) -> bytes:
    database_ready = snapshot is not None
    heartbeat_age = health.heartbeat_age_seconds()
    worker_ready = database_ready and health.is_fresh()
    worker_live = health.is_live()
    lines = [
        "# HELP dealhost_runtime_worker_process_start_time_seconds Unix time when the worker process started.",
        "# TYPE dealhost_runtime_worker_process_start_time_seconds gauge",
        _sample(
            "dealhost_runtime_worker_process_start_time_seconds", health.started_at
        ),
        "# HELP dealhost_runtime_worker_loop_heartbeat_age_seconds Seconds since the operation loop last made progress.",
        "# TYPE dealhost_runtime_worker_loop_heartbeat_age_seconds gauge",
        _sample("dealhost_runtime_worker_loop_heartbeat_age_seconds", heartbeat_age),
        "# HELP dealhost_runtime_worker_database_ready Whether the worker can query its durable operation store.",
        "# TYPE dealhost_runtime_worker_database_ready gauge",
        _sample("dealhost_runtime_worker_database_ready", 1 if database_ready else 0),
        "# HELP dealhost_runtime_worker_ready Whether the database and worker loop are ready.",
        "# TYPE dealhost_runtime_worker_ready gauge",
        _sample("dealhost_runtime_worker_ready", 1 if worker_ready else 0),
        "# HELP dealhost_runtime_worker_live Whether the operation loop heartbeat remains within its liveness deadline.",
        "# TYPE dealhost_runtime_worker_live gauge",
        _sample("dealhost_runtime_worker_live", 1 if worker_live else 0),
    ]
    if snapshot is not None:
        lines.extend(
            [
                "# HELP dealhost_runtime_operations Current durable runtime operations by status and type.",
                "# TYPE dealhost_runtime_operations gauge",
            ]
        )
        for status, operation_type, total in snapshot.operation_counts:
            lines.append(
                _sample(
                    "dealhost_runtime_operations",
                    total,
                    operation_type=operation_type,
                    status=status,
                )
            )
        lines.extend(
            [
                "# HELP dealhost_runtime_operation_queue_depth Current operation count by status.",
                "# TYPE dealhost_runtime_operation_queue_depth gauge",
            ]
        )
        for status, total in sorted(snapshot.queue_depths.items()):
            lines.append(
                _sample(
                    "dealhost_runtime_operation_queue_depth",
                    total,
                    status=status,
                )
            )
        lines.extend(
            [
                "# HELP dealhost_runtime_operation_oldest_age_seconds Age of the oldest queued or running operation.",
                "# TYPE dealhost_runtime_operation_oldest_age_seconds gauge",
            ]
        )
        for status, age in sorted(snapshot.oldest_ages.items()):
            lines.append(
                _sample(
                    "dealhost_runtime_operation_oldest_age_seconds",
                    age,
                    status=status,
                )
            )
        lines.extend(
            [
                "# HELP dealhost_runtime_operation_stale_leases Running operations whose lease is absent or expired.",
                "# TYPE dealhost_runtime_operation_stale_leases gauge",
                _sample(
                    "dealhost_runtime_operation_stale_leases",
                    snapshot.stale_leases,
                ),
                "# HELP dealhost_runtime_active_controller_failures Controller failures accumulated by queued or running operations.",
                "# TYPE dealhost_runtime_active_controller_failures gauge",
                _sample(
                    "dealhost_runtime_active_controller_failures",
                    snapshot.active_controller_failures,
                ),
                "# HELP dealhost_runtime_deployments Current managed deployments by observed state.",
                "# TYPE dealhost_runtime_deployments gauge",
            ]
        )
        for state, total in snapshot.deployment_counts:
            lines.append(
                _sample("dealhost_runtime_deployments", total, observed_state=state)
            )
    return ("\n".join(lines) + "\n").encode("utf-8")


class RuntimeWorkerMonitor:
    def __init__(
        self,
        *,
        bind: str,
        port: int,
        health: RuntimeWorkerHealth,
    ) -> None:
        self.bind = bind
        self.port = port
        self.health = health
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("runtime worker monitor is already started")
        handler = _handler_for(self.health)
        self._server = _MetricsServer((self.bind, self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="runtime-worker-monitor",
            daemon=True,
        )
        self._thread.start()

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("runtime worker monitor is not started")
        return int(self._server.server_address[1])

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


class _MetricsServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _handler_for(health: RuntimeWorkerHealth) -> type[BaseHTTPRequestHandler]:
    class RuntimeWorkerRequestHandler(BaseHTTPRequestHandler):
        server_version = "DEALHostRuntimeWorker"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/health/live":
                live = health.is_live()
                status = HTTPStatus.OK if live else HTTPStatus.SERVICE_UNAVAILABLE
                payload = (
                    b'{"status":"ok"}\n' if live else b'{"status":"unavailable"}\n'
                )
                self._send(status, payload, "application/json")
                return
            if self.path not in {"/health/ready", "/metrics"}:
                self._send(
                    HTTPStatus.NOT_FOUND,
                    b'{"status":"not_found"}\n',
                    "application/json",
                )
                return

            snapshot = None
            try:
                snapshot = collect_runtime_worker_snapshot()
            except Exception:
                logger.exception("Runtime worker monitoring database query failed")
            if self.path == "/health/ready":
                ready = snapshot is not None and health.is_fresh()
                status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
                payload = (
                    b'{"status":"ready"}\n' if ready else b'{"status":"unavailable"}\n'
                )
                self._send(status, payload, "application/json")
                return
            self._send(
                HTTPStatus.OK,
                render_runtime_worker_metrics(health, snapshot),
                "text/plain; version=0.0.4; charset=utf-8",
            )

        def log_message(self, format: str, *args) -> None:
            return

        def _send(self, status: HTTPStatus, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return RuntimeWorkerRequestHandler


def _sample(name: str, value: float | int, **labels: str) -> str:
    suffix = ""
    if labels:
        rendered = ",".join(
            f'{key}="{_escape_label(label)}"' for key, label in sorted(labels.items())
        )
        suffix = f"{{{rendered}}}"
    rendered_value = format(value, ".12g") if isinstance(value, float) else str(value)
    return f"{name}{suffix} {rendered_value}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
