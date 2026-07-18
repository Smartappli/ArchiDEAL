from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
HEALTH_PATH = ROOT / "deploy/apisix/health.py"


def load_health_module():
    spec = importlib.util.spec_from_file_location("archideal_apisix_health", HEALTH_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the APISIX health module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MetricsHandler(BaseHTTPRequestHandler):
    reachable = True

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/apisix/prometheus/metrics":
            self.send_error(404)
            return
        value = 1 if self.reachable else 0
        body = f"# TYPE apisix_etcd_reachable gauge\napisix_etcd_reachable {value}\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class ApisixHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.health = load_health_module()

    def setUp(self) -> None:
        _MetricsHandler.reachable = True
        self.metrics = ThreadingHTTPServer(("127.0.0.1", 0), _MetricsHandler)
        threading.Thread(target=self.metrics.serve_forever, daemon=True).start()
        metrics_host, metrics_port = self.metrics.server_address
        self.server = self.health.ApisixHealthServer(
            ("127.0.0.1", 0),
            f"http://{metrics_host}:{metrics_port}/apisix/prometheus/metrics",
            1.0,
        )
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.metrics.shutdown()
        self.metrics.server_close()

    def test_readiness_tracks_apisix_etcd_metric_but_liveness_does_not(self) -> None:
        host, port = self.server.server_address
        with urlopen(f"http://{host}:{port}/readyz", timeout=2) as response:
            self.assertEqual(response.status, 200)

        _MetricsHandler.reachable = False
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"http://{host}:{port}/readyz", timeout=2)
        self.assertEqual(raised.exception.code, 503)
        with urlopen(f"http://{host}:{port}/healthz", timeout=2) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"http://{host}:{port}/metrics", timeout=2)
        self.assertEqual(raised.exception.code, 404)

    def test_metric_parser_requires_an_exact_finite_reachable_sample(self) -> None:
        self.assertTrue(self.health.etcd_is_reachable(b"apisix_etcd_reachable 1\n"))
        for payload in (
            b"",
            b"apisix_etcd_reachable 0\n",
            b"apisix_etcd_reachable NaN\n",
            b"apisix_etcd_reachable_total 1\n",
        ):
            with self.subTest(payload=payload):
                self.assertFalse(self.health.etcd_is_reachable(payload))

    def test_upstream_is_restricted_to_the_loopback_apisix_metrics_path(self) -> None:
        valid = "http://127.0.0.1:9091/apisix/prometheus/metrics"
        self.assertEqual(self.health.loopback_metrics_url(valid), valid)
        for value in (
            "https://127.0.0.1:9091/apisix/prometheus/metrics",
            "http://apisix:9091/apisix/prometheus/metrics",
            "http://127.0.0.1:9091/metrics",
        ):
            with self.subTest(value=value), self.assertRaises(
                argparse.ArgumentTypeError,
            ):
                self.health.loopback_metrics_url(value)


if __name__ == "__main__":
    unittest.main()
