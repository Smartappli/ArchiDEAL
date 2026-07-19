#!/usr/bin/env python3
"""Exercise the compact-stack DEALIoT registry through its public APISIX route."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from http import HTTPStatus
from urllib import error, request


class RejectRedirects(request.HTTPRedirectHandler):
    """Keep the operator bearer credential on the exact configured origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        return None


NO_REDIRECT_OPENER = request.build_opener(RejectRedirects())


def json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    expected_error_status: int | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", **(headers or {})},
    )
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with NO_REDIRECT_OPENER.open(req, timeout=10) as response:  # noqa: S310  # nosec B310
            response_body = response.read()
            parsed = json.loads(response_body) if response_body else {}
            return response.status, parsed, dict(response.headers.items())
    except error.HTTPError as exc:
        response_body = exc.read()
        if exc.code != expected_error_status:
            detail = response_body.decode("utf-8", errors="replace")
            message = f"{method} {url} returned HTTP {exc.code}: {detail}"
            raise RuntimeError(message) from exc
        parsed = json.loads(response_body) if response_body else {}
        if not isinstance(parsed, dict):
            raise RuntimeError(
                "DEALIoT registry error response must be a JSON object"
            ) from exc
        response_headers = dict(exc.headers.items()) if exc.headers else {}
        return exc.code, parsed, response_headers


def require_device(payload: dict[str, object], device_id: str) -> dict[str, object]:
    device = payload.get("device")
    if not isinstance(device, dict) or device.get("device_id") != device_id:
        raise RuntimeError("DEALIoT registry returned an unexpected device document")
    return device


def check_registry(
    base_url: str,
    device_id: str,
    *,
    bearer_token: str | None = None,
) -> None:
    collection_url = f"{base_url.rstrip('/')}/api/devices"
    detail_url = f"{collection_url}/{device_id}"
    authorization_headers = (
        {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    )
    status, created_payload, created_headers = json_request(
        collection_url,
        method="POST",
        payload={
            "device_id": device_id,
            "display_name": "ArchiDEAL smoke device",
            "kind": "sensor",
            "status": "provisioning",
            "labels": {"purpose": "architecture-smoke"},
        },
        headers=authorization_headers,
    )
    if status != HTTPStatus.CREATED:
        raise RuntimeError(f"device registration returned unexpected HTTP {status}")
    created = require_device(created_payload, device_id)
    etag = created_headers.get("ETag") or created_headers.get("Etag")
    if etag != f'"{created.get("revision")}"':
        raise RuntimeError(
            "device registration did not return its strong revision ETag"
        )

    status, updated_payload, updated_headers = json_request(
        detail_url,
        method="PATCH",
        payload={"status": "active"},
        headers={**authorization_headers, "If-Match": etag},
    )
    if status != HTTPStatus.OK:
        raise RuntimeError(f"device update returned unexpected HTTP {status}")
    updated = require_device(updated_payload, device_id)
    updated_etag = updated_headers.get("ETag") or updated_headers.get("Etag")
    if (
        updated.get("status") != "active"
        or updated_etag != f'"{updated.get("revision")}"'
    ):
        raise RuntimeError(
            "device update did not persist the active state and revision"
        )

    stale_status, stale_payload, _stale_headers = json_request(
        detail_url,
        method="PATCH",
        payload={"display_name": "stale update must not persist"},
        headers={**authorization_headers, "If-Match": etag},
        expected_error_status=HTTPStatus.PRECONDITION_FAILED,
    )
    if (
        stale_status != HTTPStatus.PRECONDITION_FAILED
        or stale_payload.get("error") != "device_revision_conflict"
    ):
        raise RuntimeError("device registry accepted a stale revision")

    status, detail_payload, detail_headers = json_request(
        detail_url,
        headers=authorization_headers,
    )
    detail = require_device(detail_payload, device_id)
    detail_etag = detail_headers.get("ETag") or detail_headers.get("Etag")
    if (
        status != HTTPStatus.OK
        or detail.get("status") != "active"
        or detail.get("display_name") != "ArchiDEAL smoke device"
        or detail_etag != updated_etag
    ):
        raise RuntimeError("device registry read-after-write validation failed")

    status, _retired_payload, retired_headers = json_request(
        detail_url,
        method="DELETE",
        headers={**authorization_headers, "If-Match": detail_etag},
    )
    retired_etag = retired_headers.get("ETag") or retired_headers.get("Etag")
    expected_retired_etag = f'"{int(detail["revision"]) + 1}"'
    if status != HTTPStatus.NO_CONTENT or retired_etag != expected_retired_etag:
        raise RuntimeError("device retirement did not advance the revision")

    status, retired_payload, _retired_headers = json_request(
        detail_url,
        headers=authorization_headers,
        expected_error_status=HTTPStatus.NOT_FOUND,
    )
    if (
        status != HTTPStatus.NOT_FOUND
        or retired_payload.get("error") != "device_not_found"
    ):
        raise RuntimeError("retired device remains exposed by the active registry API")

    print(
        f"ok: DEALIoT registry protected stale writes and retired {device_id} "
        f"at revision {expected_retired_etag}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    http_port = os.getenv("ARCHIDEAL_HTTP_PORT", "8080")
    parser.add_argument(
        "--base-url",
        default=f"http://127.0.0.1:{http_port}/dealiot",
    )
    parser.add_argument("--device-id", required=True)
    parser.add_argument(
        "--bearer-token-file",
        help="Read the OIDC/admin bearer token from this file without exposing it in argv.",
    )
    args = parser.parse_args()
    bearer_token = None
    if args.bearer_token_file:
        bearer_token = Path(args.bearer_token_file).read_text(encoding="utf-8").strip()
        if not bearer_token:
            raise SystemExit("The bearer token file is empty.")
    check_registry(args.base_url, args.device_id, bearer_token=bearer_token)


if __name__ == "__main__":
    main()
