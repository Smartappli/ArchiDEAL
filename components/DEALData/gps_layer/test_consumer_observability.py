from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from dealdata_common.consumer_observability import (
    ConsumerMetrics,
    ConsumerMetricsServer,
    positive_float,
    positive_float_env,
)


class ConsumerObservabilityTests(unittest.TestCase):
    def test_metrics_use_bounded_results_and_measure_first_persistence_age(
        self,
    ) -> None:
        metrics = ConsumerMetrics("gps")
        event_time = datetime.now(UTC) - timedelta(seconds=2)

        metrics.record_event(
            "inserted",
            payload={"timestamp": event_time.isoformat()},
            persistence_duration_seconds=0.025,
        )
        metrics.record_event(
            "duplicate",
            payload={"timestamp": event_time.isoformat()},
            persistence_duration_seconds=0.01,
        )
        metrics.record_event(
            "rejected",
            payload=None,
            persistence_duration_seconds=0.005,
        )

        output = metrics.render_prometheus()
        self.assertIn(
            'dealdata_consumer_records_total{service="gps",result="inserted"} 1',
            output,
        )
        self.assertIn(
            'dealdata_consumer_records_total{service="gps",result="duplicate"} 1',
            output,
        )
        self.assertIn(
            'dealdata_consumer_records_total{service="gps",result="rejected"} 1',
            output,
        )
        self.assertIn(
            'dealdata_consumer_persistence_duration_seconds_count{service="gps"} 3',
            output,
        )
        self.assertIn(
            'dealdata_consumer_event_age_seconds_count{service="gps"} 1',
            output,
        )

    def test_future_or_invalid_clock_is_counted_not_added_to_age_histogram(
        self,
    ) -> None:
        metrics = ConsumerMetrics("sensor")
        future = datetime.now(UTC) + timedelta(minutes=5)

        metrics.record_event(
            "inserted",
            payload={"timestamp": future.isoformat()},
            persistence_duration_seconds=0.01,
        )

        output = metrics.render_prometheus()
        self.assertIn(
            'dealdata_consumer_invalid_event_clock_total{service="sensor"} 1',
            output,
        )
        self.assertIn(
            'dealdata_consumer_event_age_seconds_count{service="sensor"} 0',
            output,
        )

    def test_readiness_allows_standby_but_requires_database_and_healthy_fresh_poll(
        self,
    ) -> None:
        metrics = ConsumerMetrics("gps", stale_after_seconds=10)
        with patch(
            "dealdata_common.consumer_observability.time.monotonic",
            return_value=100.0,
        ):
            metrics.record_poll(kafka_assigned=False, database_ready=True)
            self.assertTrue(metrics.is_ready())
        self.assertIn(
            'dealdata_consumer_kafka_assigned{service="gps"} 0',
            metrics.render_prometheus(),
        )

        with patch(
            "dealdata_common.consumer_observability.time.monotonic",
            return_value=101.0,
        ):
            metrics.record_poll(kafka_assigned=True, database_ready=True)
            self.assertTrue(metrics.is_ready())
            metrics.record_poll_error()
            self.assertFalse(metrics.is_ready())
        self.assertIn(
            'dealdata_consumer_kafka_assigned{service="gps"} 1',
            metrics.render_prometheus(),
        )

        with patch(
            "dealdata_common.consumer_observability.time.monotonic",
            return_value=102.0,
        ):
            metrics.record_poll(kafka_assigned=False, database_ready=True)
            self.assertTrue(metrics.is_ready())
            metrics.record_database_error()
            self.assertFalse(metrics.is_ready())

        with patch(
            "dealdata_common.consumer_observability.time.monotonic",
            return_value=103.0,
        ):
            metrics.record_poll(kafka_assigned=False, database_ready=True)
        with patch(
            "dealdata_common.consumer_observability.time.monotonic",
            return_value=114.0,
        ):
            self.assertFalse(metrics.is_ready())

    def test_http_server_keeps_liveness_dependency_free(self) -> None:
        metrics = ConsumerMetrics("gps")
        server = ConsumerMetricsServer(metrics, "127.0.0.1", 0)
        server.start()
        host, port = server.address
        try:
            with urlopen(f"http://{host}:{port}/healthz", timeout=2) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(HTTPError) as raised:
                urlopen(f"http://{host}:{port}/readyz", timeout=2)
            self.assertEqual(raised.exception.code, 503)
            with urlopen(f"http://{host}:{port}/metrics", timeout=2) as response:
                self.assertIn(b"dealdata_consumer_ready", response.read())
        finally:
            server.stop()

    def test_positive_float_environment_is_fail_closed(self) -> None:
        with patch.dict(os.environ, {"TEST_POSITIVE_FLOAT": "0"}):
            with self.assertRaises(ValueError):
                positive_float_env("TEST_POSITIVE_FLOAT", 15.0)
        for value in ("0", "-1", "nan", "inf", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                positive_float(value)


if __name__ == "__main__":
    unittest.main()
