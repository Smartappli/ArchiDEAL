"""Validate the public routes and Kafka-to-DEALData persistence path."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def get(url: str):
    with urlopen(url, timeout=5) as response:
        body = response.read()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return json.loads(body)
        return body.decode("utf-8", errors="replace")


def wait_for(url: str, predicate, description: str, timeout: int = 120):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = get(url)
            if predicate(payload):
                print(f"ok: {description}")
                return payload
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"timed out waiting for {description}: {last_error}")


def health_checks(base_url: str) -> None:
    endpoints = {
        "DEALInterface": "/",
        "DEALHost": "/dealhost/api/gateway/health/",
        "DEALIoT liveness": "/dealiot/healthz",
        "DEALData Core": "/dealdata/core/health/ready/",
        "DEALData GPS": "/dealdata/gps/health/ready/",
        "DEALData Sensor": "/dealdata/sensor/health/ready/",
    }
    for label, path in endpoints.items():
        wait_for(f"{base_url}{path}", lambda _: True, label)

    health = wait_for(
        f"{base_url}/dealiot/api/health",
        lambda payload: isinstance(payload, dict),
        "DEALIoT component health",
    )
    checks = {
        item.get("id"): item
        for item in health.get("checks", [])
        if isinstance(item, dict)
    }
    for dependency in ("kafka", "mqtt"):
        check = checks.get(dependency)
        if not check or check.get("status") != "healthy":
            raise RuntimeError(f"DEALIoT cannot reach {dependency}: {check}")
        print(f"ok: DEALIoT reaches {dependency}")


def event_count(base_url: str, layer: str, device_id: str) -> int:
    query = urlencode({"device_id": device_id, "limit": 100})
    payload = get(f"{base_url}/dealdata/{layer}/api/wildfi/{layer}/?{query}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected {layer} response")
    return int(payload.get("count", 0))


def wait_for_events(base_url: str, device_id: str) -> None:
    for layer in ("gps", "sensor"):
        wait_for(
            f"{base_url}/dealdata/{layer}/api/wildfi/{layer}/?{urlencode({'device_id': device_id})}",
            lambda payload: isinstance(payload, dict) and payload.get("count") == 1,
            f"one persisted {layer} event for {device_id}",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--device-id")
    args = parser.parse_args()

    port = os.environ.get("ARCHIDEAL_HTTP_PORT", "8080")
    base_url = f"http://127.0.0.1:{port}"
    health_checks(base_url)
    if args.health_only:
        return
    if not args.device_id:
        parser.error("--device-id is required unless --health-only is used")
    wait_for_events(base_url, args.device_id)
    for layer in ("gps", "sensor"):
        count = event_count(base_url, layer, args.device_id)
        if count != 1:
            raise RuntimeError(f"expected one {layer} event, found {count}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - command boundary
        print(f"smoke check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
