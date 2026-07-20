from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.hosting.models import RuntimeOperation
from apps.hosting.runtime_observability import (
    RuntimeWorkerHealth,
    collect_runtime_worker_snapshot,
    render_runtime_worker_metrics,
)
from apps.hosting.runtime_worker import RuntimeOperationProcessor
from tests.test_runtime_management import (
    ENABLED_CONTROLLER,
    RuntimeFixtureMixin,
)


@override_settings(RUNTIME_CONTROLLER=ENABLED_CONTROLLER, RUNTIME_ENABLED=True)
class RuntimeWorkerObservabilityTests(RuntimeFixtureMixin, APITestCase):
    def test_snapshot_exposes_backlog_age_and_stale_lease_without_ids(self) -> None:
        response = self.queue_deployment(key="runtime-observability-queue")
        self.assertEqual(response.status_code, 202)
        operation = RuntimeOperation.objects.get()
        now = timezone.now()
        RuntimeOperation.objects.filter(pk=operation.pk).update(
            requested_at=now - timedelta(minutes=7),
            status=RuntimeOperation.Status.RUNNING,
            started_at=now - timedelta(minutes=7),
            next_attempt_at=None,
            lease_expires_at=now - timedelta(seconds=10),
            controller_failures=2,
        )

        snapshot = collect_runtime_worker_snapshot(now=now)

        self.assertEqual(snapshot.queue_depths[RuntimeOperation.Status.RUNNING], 1)
        self.assertGreaterEqual(
            snapshot.oldest_ages[RuntimeOperation.Status.RUNNING], 420
        )
        self.assertEqual(snapshot.stale_leases, 1)
        self.assertEqual(snapshot.active_controller_failures, 2)
        health = RuntimeWorkerHealth(heartbeat_timeout_seconds=90)
        metrics = render_runtime_worker_metrics(health, snapshot).decode()
        self.assertIn(
            'dealhost_runtime_operation_queue_depth{status="running"} 1', metrics
        )
        self.assertIn("dealhost_runtime_operation_stale_leases 1", metrics)
        self.assertNotIn(str(operation.id), metrics)

    def test_scheduled_reconciliation_is_not_reported_as_a_stale_lease(self) -> None:
        response = self.queue_deployment(key="runtime-observability-scheduled")
        self.assertEqual(response.status_code, 202)
        operation = RuntimeOperation.objects.get()
        now = timezone.now()
        RuntimeOperation.objects.filter(pk=operation.pk).update(
            status=RuntimeOperation.Status.RUNNING,
            next_attempt_at=now + timedelta(seconds=2),
            lease_token=None,
            lease_expires_at=None,
        )

        snapshot = collect_runtime_worker_snapshot(now=now)

        self.assertEqual(snapshot.stale_leases, 0)

    def test_worker_readiness_fails_when_heartbeat_becomes_stale(self) -> None:
        monotonic = [100.0]
        health = RuntimeWorkerHealth(
            heartbeat_timeout_seconds=5,
            clock=lambda: monotonic[0],
            wall_clock=lambda: 1_700_000_000.0,
        )
        snapshot = collect_runtime_worker_snapshot()
        self.assertIn(
            "dealhost_runtime_worker_ready 1",
            render_runtime_worker_metrics(health, snapshot).decode(),
        )

        monotonic[0] = 106.0

        metrics = render_runtime_worker_metrics(health, snapshot).decode()
        self.assertIn("dealhost_runtime_worker_ready 0", metrics)
        self.assertIn("dealhost_runtime_worker_loop_heartbeat_age_seconds 6", metrics)

    def test_processor_updates_heartbeat_around_each_iteration(self) -> None:
        processor = RuntimeOperationProcessor(worker_id="observability-worker")
        heartbeat = Mock()
        with patch.object(processor, "process_next", return_value=False):
            processor.run(once=True, heartbeat=heartbeat)

        self.assertEqual(heartbeat.call_count, 2)
