import unittest
from unittest.mock import patch

import httpx

from dealhost_sdk import DealHostClient


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else {"ok": True}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "https://dealhost.test"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self.payload


class FakeHttpxClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.response = FakeResponse()
        FakeHttpxClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class DealHostClientTests(unittest.TestCase):
    def setUp(self):
        FakeHttpxClient.instances = []

    @patch("dealhost_sdk.client.httpx.Client", FakeHttpxClient)
    def test_create_tool_sends_expected_request(self):
        auth_header_value = "unit-test"
        client = DealHostClient(
            "https://dealhost.test/",
            token=auth_header_value,
            timeout=5.0,
        )

        result = client.create_tool(
            name="Tool",
            slug="tool",
            description="Description",
            module_ids=[1, 2],
            enabled=False,
        )

        fake_client = FakeHttpxClient.instances[0]
        self.assertEqual({"ok": True}, result)
        self.assertEqual("https://dealhost.test", fake_client.kwargs["base_url"])
        self.assertEqual(5.0, fake_client.kwargs["timeout"])
        self.assertEqual(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {auth_header_value}",
            },
            fake_client.kwargs["headers"],
        )
        self.assertEqual(
            {
                "method": "POST",
                "url": "/api/hosting/tools/",
                "json": {
                    "name": "Tool",
                    "slug": "tool",
                    "description": "Description",
                    "module_ids": [1, 2],
                    "enabled": False,
                },
                "params": None,
            },
            fake_client.calls[0],
        )

    @patch("dealhost_sdk.client.httpx.Client", FakeHttpxClient)
    def test_create_application_defaults_module_ids_to_empty_list(self):
        client = DealHostClient("https://dealhost.test")

        client.create_application(name="App", slug="app")

        fake_client = FakeHttpxClient.instances[0]
        self.assertEqual({"Accept": "application/json"}, fake_client.kwargs["headers"])
        self.assertEqual(
            {
                "name": "App",
                "slug": "app",
                "description": "",
                "module_ids": [],
                "enabled": True,
            },
            fake_client.calls[0]["json"],
        )

    @patch("dealhost_sdk.client.httpx.Client", FakeHttpxClient)
    def test_list_tools_serializes_filters(self):
        client = DealHostClient("https://dealhost.test")

        client.list_tools(enabled=True, module_slug="analytics")

        self.assertEqual(
            {
                "method": "GET",
                "url": "/api/hosting/tools/",
                "json": None,
                "params": {"enabled": "true", "module_slug": "analytics"},
            },
            FakeHttpxClient.instances[0].calls[0],
        )

    @patch("dealhost_sdk.client.httpx.Client", FakeHttpxClient)
    def test_list_applications_omits_empty_filters(self):
        client = DealHostClient("https://dealhost.test")

        client.list_applications()

        self.assertEqual(
            {
                "method": "GET",
                "url": "/api/hosting/applications/",
                "json": None,
                "params": {},
            },
            FakeHttpxClient.instances[0].calls[0],
        )


if __name__ == "__main__":
    unittest.main()
