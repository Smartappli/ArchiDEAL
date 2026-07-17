import asyncio
import sys
import types
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.common.events import nats_client
from apps.common.events.schemas import EventEnvelope
from apps.common.events.worker import run_worker


class EventEnvelopeTests(SimpleTestCase):
    def test_to_dict_contains_expected_fields(self):
        payload = EventEnvelope(
            event_type="gateway.route.publish.requested",
            data={"module_slug": "core"},
            producer="tests",
            meta={"trace_id": "abc"},
        ).to_dict()

        self.assertIn("event_id", payload)
        self.assertEqual(payload["event_type"], "gateway.route.publish.requested")
        self.assertEqual(payload["producer"], "tests")
        self.assertEqual(payload["data"], {"module_slug": "core"})
        self.assertEqual(payload["meta"], {"trace_id": "abc"})
        self.assertIn("occurred_at", payload)


@override_settings(
    NATS={
        "URL": "nats://nats:4222",
        "STREAM": "dealhost",
        "SUBJECT_PREFIX": "dealhost",
        "ENABLED": False,
    },
)
class NatsClientDisabledTests(SimpleTestCase):
    def test_publish_disabled_returns_without_importing_nats(self):
        asyncio.run(
            nats_client._publish(
                subject="dealhost.gateway.route.publish.requested",
                payload={"ok": True},
            )
        )


@override_settings(
    NATS={
        "URL": "nats://nats:4222",
        "STREAM": "dealhost",
        "SUBJECT_PREFIX": "dealhost",
        "ENABLED": True,
    },
)
class NatsClientEnabledTests(SimpleTestCase):
    def test_publish_enabled_uses_nats_client(self):
        calls = {}

        class FakeClient:
            async def connect(self, url):
                calls["url"] = url

            async def publish(self, subject, payload):
                calls["subject"] = subject
                calls["payload"] = payload

            async def flush(self):
                calls["flushed"] = True

            async def close(self):
                calls["closed"] = True

        fake_module = types.ModuleType("nats.aio.client")
        fake_module.Client = FakeClient

        with patch.dict(sys.modules, {"nats.aio.client": fake_module}):
            asyncio.run(
                nats_client._publish("dealhost.hosting.module.created", {"id": 1})
            )

        self.assertEqual(calls["url"], "nats://nats:4222")
        self.assertEqual(calls["subject"], "dealhost.hosting.module.created")
        self.assertTrue(calls["flushed"])
        self.assertTrue(calls["closed"])

    def test_sync_publish_works_inside_running_event_loop(self):
        calls = []

        async def fake_publish(*, subject, payload):
            calls.append((subject, payload))

        async def call_sync_publish():
            nats_client.publish("dealhost.test", {"ok": True})

        with patch("apps.common.events.nats_client._publish", side_effect=fake_publish):
            asyncio.run(call_sync_publish())

        self.assertEqual(calls, [("dealhost.test", {"ok": True})])


@override_settings(
    NATS={
        "URL": "nats://nats:4222",
        "STREAM": "dealhost",
        "SUBJECT_PREFIX": "dealhost",
        "ENABLED": True,
    },
)
class WorkerTests(SimpleTestCase):
    def test_worker_subscribes_to_prefixed_subject(self):
        calls = {}

        class FakeClient:
            async def connect(self, url):
                calls["url"] = url

            async def subscribe(self, subject, cb):
                calls["subject"] = subject
                calls["cb"] = cb

        async def stop_after_first_sleep(_):
            raise asyncio.CancelledError

        with (
            patch("apps.common.events.worker.NATS", return_value=FakeClient()),
            patch(
                "apps.common.events.worker.asyncio.sleep",
                side_effect=stop_after_first_sleep,
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            asyncio.run(run_worker())

        self.assertEqual(calls["url"], "nats://nats:4222")
        self.assertEqual(calls["subject"], "dealhost.>")
