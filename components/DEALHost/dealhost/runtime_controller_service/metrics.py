from __future__ import annotations

from collections import defaultdict
import threading
import time


class RuntimeControllerMetrics:
    """Small, dependency-free Prometheus collector for the isolated controller."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_sum: dict[tuple[str, str], float] = defaultdict(float)

    def observe_request(
        self,
        *,
        method: str,
        route: str,
        status: int,
        duration_seconds: float,
    ) -> None:
        request_key = (method, route, status)
        duration_key = (method, route)
        with self._lock:
            self._requests[request_key] += 1
            self._duration_count[duration_key] += 1
            self._duration_sum[duration_key] += max(duration_seconds, 0.0)

    def render(self, *, kubernetes_ready: bool) -> bytes:
        with self._lock:
            requests = sorted(self._requests.items())
            duration_count = sorted(self._duration_count.items())
            duration_sum = dict(self._duration_sum)

        lines = [
            "# HELP dealhost_runtime_controller_process_start_time_seconds Unix time when the controller process started.",
            "# TYPE dealhost_runtime_controller_process_start_time_seconds gauge",
            _sample(
                "dealhost_runtime_controller_process_start_time_seconds",
                self.started_at,
            ),
            "# HELP dealhost_runtime_controller_kubernetes_ready Whether the Kubernetes API and controller credentials are ready.",
            "# TYPE dealhost_runtime_controller_kubernetes_ready gauge",
            _sample(
                "dealhost_runtime_controller_kubernetes_ready",
                1 if kubernetes_ready else 0,
            ),
            "# HELP dealhost_runtime_controller_requests_total Runtime-controller HTTP responses.",
            "# TYPE dealhost_runtime_controller_requests_total counter",
        ]
        for (method, route, status), value in requests:
            lines.append(
                _sample(
                    "dealhost_runtime_controller_requests_total",
                    value,
                    method=method,
                    route=route,
                    status=str(status),
                )
            )
        lines.extend(
            [
                "# HELP dealhost_runtime_controller_request_duration_seconds Runtime-controller request duration by route.",
                "# TYPE dealhost_runtime_controller_request_duration_seconds summary",
            ]
        )
        for (method, route), value in duration_count:
            labels = {"method": method, "route": route}
            lines.append(
                _sample(
                    "dealhost_runtime_controller_request_duration_seconds_count",
                    value,
                    **labels,
                )
            )
            lines.append(
                _sample(
                    "dealhost_runtime_controller_request_duration_seconds_sum",
                    duration_sum[(method, route)],
                    **labels,
                )
            )
        return ("\n".join(lines) + "\n").encode("utf-8")


def _sample(name: str, value: float | int, **labels: str) -> str:
    suffix = ""
    if labels:
        rendered = ",".join(
            f'{key}="{_escape_label(label)}"' for key, label in sorted(labels.items())
        )
        suffix = f"{{{rendered}}}"
    if isinstance(value, float):
        rendered_value = format(value, ".12g")
    else:
        rendered_value = str(value)
    return f"{name}{suffix} {rendered_value}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
