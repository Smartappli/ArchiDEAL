"""Process-local Prometheus metrics and health endpoints for Kafka consumers."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import threading
import time
from typing import Any


HISTOGRAM_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
)
DEFAULT_STALE_AFTER_SECONDS = 30.0


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _prometheus_number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return format(value, ".12g")


def positive_float(value: str) -> float:
    """Parse one finite, strictly positive floating-point value."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError("value must be a positive number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("value must be a positive number")
    return parsed


def positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return positive_float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc


def _port_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer between 1 and 65535") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be an integer between 1 and 65535")
    return value


class _Histogram:
    def __init__(self) -> None:
        self.buckets = {boundary: 0 for boundary in HISTOGRAM_BUCKETS}
        self.count = 0
        self.sum = 0.0

    def observe(self, value: float) -> None:
        if not math.isfinite(value) or value < 0:
            return
        self.count += 1
        self.sum += value
        for boundary in HISTOGRAM_BUCKETS:
            if value <= boundary:
                self.buckets[boundary] += 1


class ConsumerMetrics:
    """Thread-safe bounded-cardinality metrics for one DEALData consumer."""

    def __init__(
        self,
        service: str,
        *,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        if service not in {"gps", "sensor"}:
            raise ValueError("consumer metrics service must be gps or sensor")
        if not math.isfinite(stale_after_seconds) or stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self.service = service
        self.stale_after_seconds = stale_after_seconds
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._records: defaultdict[str, int] = defaultdict(int)
        self._commits: defaultdict[str, int] = defaultdict(int)
        self._poll_errors = 0
        self._database_errors = 0
        self._invalid_event_clocks = 0
        self._kafka_assigned = False
        self._poll_ready = False
        self._database_ready = False
        self._last_poll_monotonic: float | None = None
        self._last_poll_timestamp = 0.0
        self._persistence_duration = _Histogram()
        self._event_age = _Histogram()

    def record_poll(
        self,
        *,
        kafka_assigned: bool,
        database_ready: bool,
    ) -> None:
        """Record one successful poll and its current dependency state."""
        now_monotonic = time.monotonic()
        now = time.time()
        with self._lock:
            self._kafka_assigned = kafka_assigned
            self._poll_ready = True
            self._database_ready = database_ready
            self._last_poll_monotonic = now_monotonic
            self._last_poll_timestamp = now

    def record_poll_error(self) -> None:
        with self._lock:
            self._poll_errors += 1
            self._poll_ready = False

    def record_database_error(self) -> None:
        with self._lock:
            self._database_errors += 1
            self._database_ready = False

    def record_commit(self, result: str) -> None:
        if result not in {"success", "failure"}:
            raise ValueError("commit result must be success or failure")
        with self._lock:
            self._commits[result] += 1
            if result == "failure":
                self._poll_ready = False

    def record_event(
        self,
        result: str,
        *,
        payload: dict[str, Any] | None,
        persistence_duration_seconds: float,
    ) -> None:
        """Record an insertion, duplicate or rejection without unbounded labels."""
        if result not in {"inserted", "duplicate", "rejected"}:
            raise ValueError("unsupported consumer event result")
        now = datetime.now(UTC)
        with self._lock:
            self._records[result] += 1
            self._persistence_duration.observe(persistence_duration_seconds)
            if result != "inserted":
                return
            event_time = self._parse_event_time(payload)
            if event_time is None:
                self._invalid_event_clocks += 1
                return
            age = (now - event_time).total_seconds()
            if age < 0:
                self._invalid_event_clocks += 1
                return
            self._event_age.observe(age)

    @staticmethod
    def _parse_event_time(payload: dict[str, Any] | None) -> datetime | None:
        if not payload:
            return None
        value = payload.get("timestamp")
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC)

    def mark_not_ready(self) -> None:
        with self._lock:
            self._kafka_assigned = False
            self._poll_ready = False

    def is_ready(self) -> bool:
        with self._lock:
            if not self._poll_ready or not self._database_ready:
                return False
            last_poll = self._last_poll_monotonic
        return (
            last_poll is not None
            and time.monotonic() - last_poll <= self.stale_after_seconds
        )

    def render_prometheus(self) -> str:
        """Render a stable Prometheus text exposition snapshot."""
        with self._lock:
            records = dict(self._records)
            commits = dict(self._commits)
            poll_errors = self._poll_errors
            database_errors = self._database_errors
            invalid_event_clocks = self._invalid_event_clocks
            kafka_assigned = self._kafka_assigned
            database_ready = self._database_ready
            last_poll_timestamp = self._last_poll_timestamp
            persistence = self._copy_histogram(self._persistence_duration)
            event_age = self._copy_histogram(self._event_age)
        service = _escape_label(self.service)
        labels = f'service="{service}"'
        lines = [
            "# HELP dealdata_consumer_ready Whether the database is reachable and the Kafka poll loop is healthy and fresh.",
            "# TYPE dealdata_consumer_ready gauge",
            f"dealdata_consumer_ready{{{labels}}} {int(self.is_ready())}",
            "# HELP dealdata_consumer_kafka_assigned Whether the consumer currently has at least one Kafka partition assignment.",
            "# TYPE dealdata_consumer_kafka_assigned gauge",
            f"dealdata_consumer_kafka_assigned{{{labels}}} {int(kafka_assigned)}",
            "# HELP dealdata_consumer_database_ready Whether the most recent database readiness check succeeded.",
            "# TYPE dealdata_consumer_database_ready gauge",
            f"dealdata_consumer_database_ready{{{labels}}} {int(database_ready)}",
            "# HELP dealdata_consumer_last_successful_poll_timestamp_seconds Unix timestamp of the most recent successful Kafka poll.",
            "# TYPE dealdata_consumer_last_successful_poll_timestamp_seconds gauge",
            f"dealdata_consumer_last_successful_poll_timestamp_seconds{{{labels}}} {_prometheus_number(last_poll_timestamp)}",
            "# HELP dealdata_consumer_process_start_time_seconds Unix timestamp when this consumer process started.",
            "# TYPE dealdata_consumer_process_start_time_seconds gauge",
            f"dealdata_consumer_process_start_time_seconds{{{labels}}} {_prometheus_number(self.started_at)}",
            "# HELP dealdata_consumer_records_total Kafka records handled by bounded result.",
            "# TYPE dealdata_consumer_records_total counter",
        ]
        for result in ("inserted", "duplicate", "rejected"):
            lines.append(
                f'dealdata_consumer_records_total{{{labels},result="{result}"}} {records.get(result, 0)}'
            )
        lines.extend(
            [
                "# HELP dealdata_consumer_commits_total Kafka offset commit attempts by result.",
                "# TYPE dealdata_consumer_commits_total counter",
                f'dealdata_consumer_commits_total{{{labels},result="success"}} {commits.get("success", 0)}',
                f'dealdata_consumer_commits_total{{{labels},result="failure"}} {commits.get("failure", 0)}',
                "# HELP dealdata_consumer_poll_errors_total Kafka poll failures.",
                "# TYPE dealdata_consumer_poll_errors_total counter",
                f"dealdata_consumer_poll_errors_total{{{labels}}} {poll_errors}",
                "# HELP dealdata_consumer_database_errors_total Database checks or persistence failures.",
                "# TYPE dealdata_consumer_database_errors_total counter",
                f"dealdata_consumer_database_errors_total{{{labels}}} {database_errors}",
                "# HELP dealdata_consumer_invalid_event_clock_total Inserted events whose source timestamp cannot produce a valid age.",
                "# TYPE dealdata_consumer_invalid_event_clock_total counter",
                f"dealdata_consumer_invalid_event_clock_total{{{labels}}} {invalid_event_clocks}",
            ]
        )
        lines.extend(
            self._render_histogram(
                "dealdata_consumer_persistence_duration_seconds",
                "Time spent decoding and persisting one consumed record.",
                labels,
                persistence,
            )
        )
        lines.extend(
            self._render_histogram(
                "dealdata_consumer_event_age_seconds",
                "Age from the source event timestamp to a successful first persistence.",
                labels,
                event_age,
            )
        )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _copy_histogram(histogram: _Histogram) -> _Histogram:
        copied = _Histogram()
        copied.buckets = dict(histogram.buckets)
        copied.count = histogram.count
        copied.sum = histogram.sum
        return copied

    @staticmethod
    def _render_histogram(
        name: str,
        help_text: str,
        labels: str,
        histogram: _Histogram,
    ) -> list[str]:
        lines = [f"# HELP {name} {help_text}", f"# TYPE {name} histogram"]
        for boundary in HISTOGRAM_BUCKETS:
            lines.append(
                f'{name}_bucket{{{labels},le="{_prometheus_number(boundary)}"}} {histogram.buckets[boundary]}'
            )
        lines.extend(
            [
                f'{name}_bucket{{{labels},le="+Inf"}} {histogram.count}',
                f"{name}_sum{{{labels}}} {_prometheus_number(histogram.sum)}",
                f"{name}_count{{{labels}}} {histogram.count}",
            ]
        )
        return lines


class _ConsumerHandler(BaseHTTPRequestHandler):
    metrics: ConsumerMetrics

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._respond(HTTPStatus.OK, b'{"status":"alive"}\n', "application/json")
            return
        if path == "/readyz":
            ready = self.metrics.is_ready()
            body = (
                json.dumps({"status": "ready" if ready else "not_ready"}).encode()
                + b"\n"
            )
            self._respond(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                body,
                "application/json",
            )
            return
        if path == "/metrics":
            self._respond(
                HTTPStatus.OK,
                self.metrics.render_prometheus().encode(),
                "text/plain; version=0.0.4; charset=utf-8",
            )
            return
        self._respond(
            HTTPStatus.NOT_FOUND, b'{"detail":"not found"}\n', "application/json"
        )

    def _respond(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, message_format: str, *args: Any) -> None:
        del message_format, args


class ConsumerMetricsServer:
    def __init__(self, metrics: ConsumerMetrics, bind: str, port: int) -> None:
        handler = type(
            f"{metrics.service.title()}ConsumerHandler",
            (_ConsumerHandler,),
            {"metrics": metrics},
        )
        self._server = ThreadingHTTPServer((bind, port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"{metrics.service}-consumer-observability",
            daemon=True,
        )

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def start_consumer_metrics_server(
    service: str,
) -> tuple[ConsumerMetrics, ConsumerMetricsServer]:
    """Start the process-local health and metrics endpoint for one consumer."""
    metrics = ConsumerMetrics(
        service,
        stale_after_seconds=positive_float_env(
            "DEALDATA_CONSUMER_STALE_AFTER_SECONDS",
            DEFAULT_STALE_AFTER_SECONDS,
        ),
    )
    server = ConsumerMetricsServer(
        metrics,
        os.environ.get("DEALDATA_CONSUMER_METRICS_BIND", "0.0.0.0"),
        _port_env("DEALDATA_CONSUMER_METRICS_PORT", 9100),
    )
    server.start()
    return metrics, server
