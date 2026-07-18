#!/usr/bin/env python3
"""Expose APISIX process health and dependency-aware readiness."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import math
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_METRICS_BYTES = 1024 * 1024
ETCD_METRIC = re.compile(r"^apisix_etcd_reachable(?:\{[^{}\n]*\})?$")


def loopback_metrics_url(value: str) -> str:
    """Accept only the fixed APISIX Prometheus endpoint on loopback."""
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/apisix/prometheus/metrics"
        or parsed.port is None
    ):
        raise argparse.ArgumentTypeError(
            "upstream must be an explicit loopback APISIX Prometheus URL",
        )
    return value


def etcd_is_reachable(metrics: bytes) -> bool:
    """Require every exported APISIX etcd reachability sample to equal one."""
    samples: list[float] = []
    for raw_line in metrics.decode("utf-8", errors="strict").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2 or not ETCD_METRIC.fullmatch(fields[0]):
            continue
        value = float(fields[1])
        samples.append(value)
    return bool(samples) and all(math.isfinite(value) and value == 1.0 for value in samples)


class ApisixHealthServer(ThreadingHTTPServer):
    """HTTP server carrying one immutable loopback metrics endpoint."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        upstream: str,
        timeout: float,
    ) -> None:
        self.upstream = upstream
        self.upstream_timeout = timeout
        super().__init__(address, ApisixHealthHandler)


class ApisixHealthHandler(BaseHTTPRequestHandler):
    """Keep liveness cheap while gating readiness on APISIX-to-etcd state."""

    server: ApisixHealthServer

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._respond(HTTPStatus.OK, b"ok\n")
            return
        if path != "/readyz":
            self._respond(HTTPStatus.NOT_FOUND, b"not found\n")
            return
        try:
            request = Request(self.server.upstream, headers={"Accept": "text/plain"})
            with urlopen(request, timeout=self.server.upstream_timeout) as response:
                body = response.read(MAX_METRICS_BYTES + 1)
            if len(body) > MAX_METRICS_BYTES or not etcd_is_reachable(body):
                raise ValueError("APISIX does not report etcd as reachable")
        except (
            HTTPError,
            URLError,
            OSError,
            TimeoutError,
            UnicodeDecodeError,
            ValueError,
        ):
            self._respond(HTTPStatus.SERVICE_UNAVAILABLE, b"not ready\n")
            return
        self._respond(HTTPStatus.OK, b"ready\n")

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.do_GET()

    def _respond(self, status: HTTPStatus, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=loopback_metrics_url)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9191)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    server = ApisixHealthServer((args.bind, args.port), args.upstream, args.timeout)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
