from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.common.events.publisher import publish_event


@override_settings(
    NATS={
        "URL": "nats://nats:4222",
        "STREAM": "dealhost",
        "SUBJECT_PREFIX": "dealhost",
        "ENABLED": True,
    },
)
class EventPublisherTests(SimpleTestCase):
    @patch("apps.common.events.publisher.publish")
    def test_publish_event_prefixes_subject(self, publish_mock):
        publish_event(
            event_type="gateway.route.publish.requested",
            data={"module_slug": "core"},
            producer="tests",
        )

        publish_mock.assert_called_once()
        kwargs = publish_mock.call_args.kwargs
        self.assertEqual(kwargs["subject"], "dealhost.gateway.route.publish.requested")
        self.assertEqual(
            kwargs["payload"]["event_type"],
            "gateway.route.publish.requested",
        )
