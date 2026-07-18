"""Expose only a loopback Django metrics endpoint to the monitoring network."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_METRICS_BYTES = 5 * 1024 * 1024
MAX_READINESS_BYTES = 64 * 1024


def _loopback_upstream_url(value: str, *, path: str, purpose: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != path
        or parsed.port is None
    ):
        raise argparse.ArgumentTypeError(
            f"{purpose} upstream must be an explicit loopback HTTP URL ending in {path}",
        )
    return value


def loopback_metrics_url(value: str) -> str:
    """Validate a fixed, local-only upstream metrics URL."""
    return _loopback_upstream_url(value, path="/metrics/", purpose="metrics")


def loopback_ready_url(value: str) -> str:
    """Validate a fixed, local-only upstream readiness URL."""
    return _loopback_upstream_url(value, path="/health/ready/", purpose="readiness")


def host_header(value: str) -> str:
    """Accept one explicit internal DNS label for Django ALLOWED_HOSTS."""
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 63
        or normalized[0] == "-"
        or normalized[-1] == "-"
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in normalized)
    ):
        raise argparse.ArgumentTypeError("host header must be one lowercase DNS label")
    return normalized


class MetricsProxyServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying one immutable loopback upstream."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        upstream: str,
        ready_upstream: str,
        upstream_host: str,
        timeout: float,
    ) -> None:
        self.upstream = upstream
        self.ready_upstream = ready_upstream
        self.upstream_host = upstream_host
        self.upstream_timeout = timeout
        super().__init__(address, MetricsProxyHandler)


class MetricsProxyHandler(BaseHTTPRequestHandler):
    """Serve health and metrics while rejecting every application path."""

    server: MetricsProxyServer

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._respond(HTTPStatus.OK, b"ok\n", "text/plain; charset=utf-8")
            return
        if path not in {"/readyz", "/metrics"}:
            self._respond(
                HTTPStatus.NOT_FOUND,
                b"not found\n",
                "text/plain; charset=utf-8",
            )
            return
        upstream = self.server.ready_upstream if path == "/readyz" else self.server.upstream
        byte_limit = MAX_READINESS_BYTES if path == "/readyz" else MAX_METRICS_BYTES
        try:
            body, content_type = self._fetch(upstream, byte_limit)
        except (HTTPError, URLError, OSError, ValueError):
            self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                b"metrics unavailable\n",
                "text/plain; charset=utf-8",
            )
            return
        if path == "/readyz":
            self._respond(HTTPStatus.OK, b"ready\n", "text/plain; charset=utf-8")
            return
        self._respond(HTTPStatus.OK, body, content_type)

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.do_GET()

    def _fetch(self, upstream: str, byte_limit: int) -> tuple[bytes, str]:
        request = Request(
            upstream,
            headers={
                "Host": self.server.upstream_host,
                "X-Forwarded-Proto": "https",
            },
        )
        with urlopen(request, timeout=self.server.upstream_timeout) as response:
            body = response.read(byte_limit + 1)
            if len(body) > byte_limit:
                raise ValueError("upstream response exceeds the configured bound")
            content_type = response.headers.get_content_type()
        return body, content_type

    def _respond(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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
    parser.add_argument("--upstream-ready", required=True, type=loopback_ready_url)
    parser.add_argument("--upstream-host", required=True, type=host_header)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9101)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    server = MetricsProxyServer(
        (args.bind, args.port),
        args.upstream,
        args.upstream_ready,
        args.upstream_host,
        args.timeout,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
