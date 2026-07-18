"""Validate the public routes and DEALData persistence contracts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import sys
import time
from typing import Any, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
    urlopen,
)
import uuid


class HTTPResult(NamedTuple):
    """An HTTP response, including non-success statuses used by negative tests."""

    status: int
    payload: object
    final_url: str
    headers: dict[str, str]


class NoRedirectHandler(HTTPRedirectHandler):
    """Expose redirects to the caller instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


def _token_headers(
    environment_name: str,
    header_name: str,
    prefix: str = "",
) -> dict[str, str]:
    """Load a token from a file without exposing the value in argv or errors."""
    token_file = os.environ.get(environment_name, "").strip()
    if not token_file:
        return {}
    token = Path(token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"{environment_name} is empty")
    return {header_name: f"{prefix}{token}"}


def request_headers() -> dict[str, str]:
    """Load an optional short-lived bearer token without exposing it in argv."""
    return _token_headers(
        "ARCHIDEAL_BEARER_TOKEN_FILE",
        "Authorization",
        "Bearer ",
    )


def ingest_headers() -> dict[str, str]:
    """Load the DEALData write token independently from the edge credential."""
    return _token_headers(
        "ARCHIDEAL_INGEST_TOKEN_FILE",
        "X-DEALDATA-INGEST-TOKEN",
    )


def tls_context() -> ssl.SSLContext:
    """Use system trust or the explicitly supplied production CA bundle."""
    ca_file = os.environ.get("ARCHIDEAL_CA_FILE", "").strip() or None
    return ssl.create_default_context(cafile=ca_file)


def _decode_response(response) -> HTTPResult:  # noqa: ANN001
    response_headers = {
        str(key).lower(): str(value) for key, value in response.headers.items()
    }
    body = response.read()
    content_type = response_headers.get("content-type", "")
    if "application/json" in content_type and body:
        payload: object = json.loads(body)
    else:
        payload = body.decode("utf-8", errors="replace")
    return HTTPResult(
        status=int(response.status),
        payload=payload,
        final_url=response.geturl(),
        headers=response_headers,
    )


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: object | None = None,
    follow_redirects: bool = True,
) -> HTTPResult:
    """Issue a request while keeping expected 3xx/4xx responses inspectable."""
    request_headers_value = dict(headers or {})
    body: bytes | None = None
    if json_body is not None:
        body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
        request_headers_value.setdefault("Content-Type", "application/json")
    request = Request(
        url,
        data=body,
        headers=request_headers_value,
        method=method,
    )
    try:
        if follow_redirects:
            with urlopen(request, timeout=5, context=tls_context()) as response:
                return _decode_response(response)
        opener = build_opener(
            HTTPSHandler(context=tls_context()),
            NoRedirectHandler(),
        )
        with opener.open(request, timeout=5) as response:
            return _decode_response(response)
    except HTTPError as exc:
        return _decode_response(exc)


def _same_endpoint(requested_url: str, final_url: str) -> bool:
    requested = urlsplit(requested_url)
    final = urlsplit(final_url)
    return (final.scheme, final.netloc, final.path.rstrip("/")) == (
        requested.scheme,
        requested.netloc,
        requested.path.rstrip("/"),
    )


def get(url: str):
    result = http_request(url, headers=request_headers())
    if not 200 <= result.status < 300:
        raise RuntimeError(
            f"GET {urlsplit(url).path} returned HTTP {result.status}"
        )
    if not _same_endpoint(url, result.final_url):
        raise RuntimeError(
            f"GET {urlsplit(url).path} was unexpectedly redirected"
        )
    return result.payload


def wait_for(url: str, predicate, description: str, timeout: int = 120):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = get(url)
            if predicate(payload):
                print(f"ok: {description}")
                return payload
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"timed out waiting for {description}: {last_error}")


def health_checks(base_url: str) -> None:
    endpoints = {
        "DEALInterface": (
            "/",
            lambda payload: isinstance(payload, str) and 'id="root"' in payload,
        ),
        "DEALHost": (
            "/dealhost/api/gateway/health/ready/",
            lambda payload: service_is_ready(payload, "gateway"),
        ),
        "DEALIoT liveness": (
            "/dealiot/healthz",
            lambda payload: isinstance(payload, dict) and payload.get("status") == "ok",
        ),
        "DEALData Core": (
            "/dealdata/core/health/ready/",
            lambda payload: service_is_ready(payload, "core", require_database=True),
        ),
        "DEALData GPS": (
            "/dealdata/gps/health/ready/",
            lambda payload: service_is_ready(payload, "gps", require_database=True),
        ),
        "DEALData Sensor": (
            "/dealdata/sensor/health/ready/",
            lambda payload: service_is_ready(payload, "sensor", require_database=True),
        ),
    }
    for label, (path, predicate) in endpoints.items():
        wait_for(f"{base_url}{path}", predicate, label)

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
    dependencies = {"kafka": "Kafka", "vernemq": "MQTT"}
    for dependency, label in dependencies.items():
        check = checks.get(dependency)
        if not check or check.get("status") != "healthy":
            raise RuntimeError(f"DEALIoT cannot reach {label}: {check}")
        print(f"ok: DEALIoT reaches {label}")


def service_is_ready(
    payload: object,
    service: str,
    *,
    require_database: bool = False,
) -> bool:
    """Reject login/error pages that happen to return HTTP 200 during smoke tests."""
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "ok" or payload.get("service") != service:
        return False
    return not require_database or payload.get("database") == "available"


def event_count(base_url: str, layer: str, device_id: str) -> int:
    query = urlencode({"device_id": device_id, "limit": 100})
    payload = get(f"{base_url}/dealdata/{layer}/api/wildfi/{layer}/?{query}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected {layer} response")
    return int(payload.get("count", 0))


def wait_for_events(base_url: str, device_id: str) -> None:
    for layer in ("gps", "sensor"):
        query = urlencode({"device_id": device_id})
        wait_for(
            f"{base_url}/dealdata/{layer}/api/wildfi/{layer}/?{query}",
            lambda payload: isinstance(payload, dict) and payload.get("count") == 1,
            f"one persisted {layer} event for {device_id}",
        )


def production_auth_checks(base_url: str) -> None:
    """Prove protected business access and the only anonymous edge exception."""
    repositories_url = f"{base_url}/dealhost/api/gateway/github/repositories/"
    authenticated = http_request(
        repositories_url,
        headers=request_headers(),
        follow_redirects=False,
    )
    if (
        authenticated.status != 200
        or not _same_endpoint(repositories_url, authenticated.final_url)
        or not isinstance(authenticated.payload, dict)
        or not isinstance(authenticated.payload.get("repositories"), list)
    ):
        raise RuntimeError(
            "authenticated DEALHost business route did not return repositories"
        )
    print("ok: OIDC bearer reaches the DEALHost business API")

    anonymous = http_request(
        repositories_url,
        headers={},
        follow_redirects=False,
    )
    if anonymous.status not in {302, 401, 403}:
        raise RuntimeError(
            "anonymous DEALHost business request was not rejected at the edge"
        )
    print("ok: anonymous DEALHost business request is rejected without redirect follow")

    webhook_url = f"{base_url}/dealhost/api/gateway/github/webhook/"
    unsigned = http_request(
        webhook_url,
        method="POST",
        headers={},
        json_body={},
        follow_redirects=False,
    )
    if unsigned.status != 401:
        raise RuntimeError(
            "unsigned anonymous webhook did not reach DEALHost HMAC validation"
        )
    print("ok: unsigned anonymous webhook is rejected by DEALHost")


def _ingest_payloads(device_id: str, run_id: str) -> dict[str, dict[str, Any]]:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    common = {
        "device_id": device_id,
        "timestamp": timestamp,
        "source": "archideal-production-smoke",
    }
    return {
        "gps": {
            **common,
            "event_id": f"archideal-smoke-gps-{run_id}",
            "mqtt_topic": f"wildfi/{device_id}/gps",
            "latitude": 50.6333,
            "longitude": 5.5667,
            "altitude_m": 121.5,
            "speed_m_s": 1.8,
            "heading_deg": 84.5,
            "payload": {"fix": 3, "hdop": 0.9},
        },
        "sensor": {
            **common,
            "event_id": f"archideal-smoke-sensor-{run_id}",
            "mqtt_topic": f"wildfi/{device_id}/sensor",
            "payload": {
                "sensor_type": "temperature",
                "value": 18.5,
                "unit": "C",
            },
        },
    }


def exercise_api_ingest(base_url: str) -> None:
    """Create, replay and query unique GPS and sensor events through the edge."""
    run_id = uuid.uuid4().hex
    device_id = f"archideal-smoke-{run_id}"
    payloads = _ingest_payloads(device_id, run_id)
    headers = {**request_headers(), **ingest_headers()}

    for layer, payload in payloads.items():
        url = f"{base_url}/dealdata/{layer}/api/ingest/wildfi/{layer}/"
        created = http_request(
            url,
            method="POST",
            headers=headers,
            json_body=payload,
            follow_redirects=False,
        )
        if (
            created.status != 201
            or not _same_endpoint(url, created.final_url)
            or not isinstance(created.payload, dict)
            or created.payload.get("duplicate") is not False
        ):
            raise RuntimeError(f"first {layer} ingest did not create one event")

        replayed = http_request(
            url,
            method="POST",
            headers=headers,
            json_body=payload,
            follow_redirects=False,
        )
        if (
            replayed.status != 200
            or not _same_endpoint(url, replayed.final_url)
            or not isinstance(replayed.payload, dict)
            or replayed.payload.get("duplicate") is not True
        ):
            raise RuntimeError(f"replayed {layer} ingest was not deduplicated")
        print(f"ok: {layer} API ingest is idempotent")

    wait_for_events(base_url, device_id)
    for layer in ("gps", "sensor"):
        count = event_count(base_url, layer, device_id)
        if count != 1:
            raise RuntimeError(f"expected one {layer} event, found {count}")
        print(f"ok: exactly one {layer} API event persisted")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--device-id")
    parser.add_argument(
        "--exercise-api-ingest",
        action="store_true",
        help="create and replay unique GPS and sensor events through the edge",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="require HTTPS and a bearer token file for the protected edge",
    )
    args = parser.parse_args()

    port = os.environ.get("ARCHIDEAL_HTTP_PORT", "8080")
    base_url = os.environ.get(
        "ARCHIDEAL_BASE_URL",
        f"http://127.0.0.1:{port}",
    ).rstrip("/")
    if args.production:
        if not base_url.startswith("https://"):
            parser.error("--production requires an https:// ARCHIDEAL_BASE_URL")
        if not os.environ.get("ARCHIDEAL_BEARER_TOKEN_FILE", "").strip():
            parser.error("--production requires ARCHIDEAL_BEARER_TOKEN_FILE")
    if args.health_only and args.exercise_api_ingest:
        parser.error("--health-only cannot be combined with --exercise-api-ingest")
    if args.exercise_api_ingest and not os.environ.get(
        "ARCHIDEAL_INGEST_TOKEN_FILE", ""
    ).strip():
        parser.error(
            "--exercise-api-ingest requires ARCHIDEAL_INGEST_TOKEN_FILE"
        )

    health_checks(base_url)
    if args.health_only:
        return
    if args.production:
        production_auth_checks(base_url)
    if args.exercise_api_ingest:
        exercise_api_ingest(base_url)
    if args.device_id:
        wait_for_events(base_url, args.device_id)
        for layer in ("gps", "sensor"):
            count = event_count(base_url, layer, args.device_id)
            if count != 1:
                raise RuntimeError(f"expected one {layer} event, found {count}")
    elif not args.exercise_api_ingest:
        parser.error(
            "--device-id or --exercise-api-ingest is required unless --health-only is used"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - command boundary
        print(f"smoke check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
