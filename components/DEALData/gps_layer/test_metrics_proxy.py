"""Security tests for the monitoring-only DEALData metrics proxy."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from dealdata_common.metrics_proxy import (
    MetricsProxyServer,
    host_header,
    loopback_metrics_url,
    loopback_ready_url,
)


class _UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/metrics/" and self.headers.get("Host") == "dealdata-gps":
            body = b"dealdata_test_metric 1\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/health/ready/" and self.headers.get("Host") == "dealdata-gps":
            body = b'{"status":"ok","database":"available"}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class MetricsProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
        upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        upstream_thread.start()
        upstream_host, upstream_port = self.upstream.server_address
        self.proxy = MetricsProxyServer(
            ("127.0.0.1", 0),
            f"http://{upstream_host}:{upstream_port}/metrics/",
            f"http://{upstream_host}:{upstream_port}/health/ready/",
            "dealdata-gps",
            1.0,
        )
        proxy_thread = threading.Thread(target=self.proxy.serve_forever, daemon=True)
        proxy_thread.start()

    def tearDown(self) -> None:
        self.proxy.shutdown()
        self.proxy.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def test_proxy_exposes_metrics_but_never_application_paths(self) -> None:
        host, port = self.proxy.server_address
        with urlopen(f"http://{host}:{port}/metrics", timeout=2) as response:
            self.assertEqual(response.read(), b"dealdata_test_metric 1\n")
        with urlopen(f"http://{host}:{port}/readyz", timeout=2) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"http://{host}:{port}/api/wildfi/gps/", timeout=2)
        self.assertEqual(raised.exception.code, 404)

    def test_upstream_must_be_explicit_loopback_metrics_path(self) -> None:
        self.assertEqual(
            loopback_metrics_url("http://127.0.0.1:7001/metrics/"),
            "http://127.0.0.1:7001/metrics/",
        )
        self.assertEqual(
            loopback_ready_url("http://127.0.0.1:7001/health/ready/"),
            "http://127.0.0.1:7001/health/ready/",
        )
        for value in (
            "https://127.0.0.1:7001/metrics/",
            "http://dealdata-gps:7001/metrics/",
            "http://127.0.0.1:7001/api/wildfi/gps/",
        ):
            with self.subTest(value=value), self.assertRaises(
                argparse.ArgumentTypeError,
            ):
                loopback_metrics_url(value)
        for value in (
            "https://127.0.0.1:7001/health/ready/",
            "http://dealdata-gps:7001/health/ready/",
            "http://127.0.0.1:7001/metrics/",
        ):
            with self.subTest(value=value), self.assertRaises(
                argparse.ArgumentTypeError,
            ):
                loopback_ready_url(value)
        self.assertEqual(host_header("dealdata-gps"), "dealdata-gps")
        for value in ("", "DealData GPS", "-dealdata"):
            with self.subTest(value=value), self.assertRaises(
                argparse.ArgumentTypeError,
            ):
                host_header(value)


if __name__ == "__main__":
    unittest.main()
