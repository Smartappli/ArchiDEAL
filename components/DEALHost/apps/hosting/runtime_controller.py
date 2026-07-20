from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote

import httpx
from django.conf import settings

from dealhost.settings.env import RuntimeControllerConfig


ALLOWED_RUNTIME_STATES = {
    "pending",
    "reconciling",
    "running",
    "stopped",
    "degraded",
    "failed",
    "deleting",
    "deleted",
    "unknown",
}
MAX_CONTROLLER_RESPONSE_BYTES = 2 * 1024 * 1024


class RuntimeControllerUnavailable(RuntimeError):
    pass


class RuntimeControllerError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RuntimeSnapshot:
    controller_id: str
    state: str
    message: str
    observed_generation: int
    components: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RuntimeLogs:
    lines: tuple[str, ...]
    cursor: str
    truncated: bool


class RuntimeControllerClient:
    """Small, fail-closed client for an isolated deployment controller."""

    def __init__(self, config: RuntimeControllerConfig | None = None) -> None:
        self.config = config or settings.RUNTIME_CONTROLLER

    def ensure_configured(self) -> None:
        if not self.config.configured:
            raise RuntimeControllerUnavailable(
                "Runtime deployment is unavailable until an isolated controller is configured."
            )

    def deploy(self, payload: dict[str, Any], *, request_id: str) -> RuntimeSnapshot:
        data = self._request(
            "POST",
            "/v1/deployments",
            request_id=request_id,
            json=payload,
            expected_statuses={200, 201, 202},
        )
        return _snapshot(data, require_id=True)

    def update(
        self,
        controller_id: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> RuntimeSnapshot:
        data = self._request(
            "PUT",
            f"/v1/deployments/{_identifier(controller_id)}",
            request_id=request_id,
            json=payload,
            expected_statuses={200, 202},
        )
        return _snapshot(data, fallback_id=controller_id)

    def action(
        self,
        controller_id: str,
        action_name: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> RuntimeSnapshot:
        if action_name not in {"start", "stop", "restart", "redeploy"}:
            raise ValueError("Unsupported runtime action.")
        data = self._request(
            "POST",
            f"/v1/deployments/{_identifier(controller_id)}/actions/{action_name}",
            request_id=request_id,
            json=payload,
            expected_statuses={200, 202},
        )
        return _snapshot(data, fallback_id=controller_id)

    def undeploy(self, controller_id: str, *, request_id: str) -> RuntimeSnapshot:
        data = self._request(
            "DELETE",
            f"/v1/deployments/{_identifier(controller_id)}",
            request_id=request_id,
            expected_statuses={200, 202},
        )
        return _snapshot(data, fallback_id=controller_id)

    def status(self, controller_id: str, *, request_id: str) -> RuntimeSnapshot:
        data = self._request(
            "GET",
            f"/v1/deployments/{_identifier(controller_id)}",
            request_id=request_id,
            expected_statuses={200},
        )
        return _snapshot(data, fallback_id=controller_id)

    def logs(
        self,
        controller_id: str,
        *,
        tail: int,
        request_id: str,
    ) -> RuntimeLogs:
        data = self._request(
            "GET",
            f"/v1/deployments/{_identifier(controller_id)}/logs",
            request_id=request_id,
            params={"tail": tail},
            expected_statuses={200},
        )
        raw_lines = data.get("lines")
        if not isinstance(raw_lines, list) or len(raw_lines) > tail:
            raise RuntimeControllerError("Runtime controller returned an invalid log response.")
        lines: list[str] = []
        total = 0
        for value in raw_lines:
            if not isinstance(value, str):
                raise RuntimeControllerError(
                    "Runtime controller returned an invalid log response."
                )
            line = value.replace("\x00", "")[:16_384]
            total += len(line)
            if total > 1_000_000:
                raise RuntimeControllerError("Runtime controller log response is too large.")
            lines.append(line)
        cursor = data.get("cursor", "")
        if not isinstance(cursor, str) or len(cursor) > 500:
            raise RuntimeControllerError("Runtime controller returned an invalid log cursor.")
        truncated = data.get("truncated", False)
        if not isinstance(truncated, bool):
            raise RuntimeControllerError("Runtime controller returned an invalid log response.")
        return RuntimeLogs(tuple(lines), cursor, truncated)

    def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str,
        expected_statuses: set[int],
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_configured()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.token}",
            "Idempotency-Key": request_id,
            "X-Request-ID": request_id,
        }
        try:
            with httpx.Client(
                base_url=self.config.base_url,
                follow_redirects=False,
                timeout=self.config.timeout_seconds,
                trust_env=False,
            ) as client:
                response = client.request(
                    method,
                    path,
                    headers=headers,
                    json=json,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise RuntimeControllerError(
                "Runtime controller could not be reached.",
            ) from exc

        if response.status_code not in expected_statuses:
            raise RuntimeControllerError(
                f"Runtime controller rejected the request (HTTP {response.status_code}).",
                status_code=response.status_code,
            )
        if len(response.content) > MAX_CONTROLLER_RESPONSE_BYTES:
            raise RuntimeControllerError("Runtime controller response is too large.")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            raise RuntimeControllerError("Runtime controller returned a non-JSON response.")
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeControllerError(
                "Runtime controller returned malformed JSON."
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeControllerError("Runtime controller returned an invalid response.")
        return data


def _identifier(value: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)
        or value in {".", ".."}
        or "%" in value
    ):
        raise RuntimeControllerError("Runtime controller identifier is invalid.")
    return quote(value, safe="")


def _snapshot(
    data: dict[str, Any],
    *,
    fallback_id: str = "",
    require_id: bool = False,
) -> RuntimeSnapshot:
    controller_id = data.get("id", fallback_id)
    state = data.get("state")
    message = data.get("message", "")
    observed_generation = data.get("observed_generation")
    components = data.get("components")
    if (
        not isinstance(controller_id, str)
        or not controller_id
        or len(controller_id) > 128
        or (require_id and controller_id == fallback_id == "")
    ):
        raise RuntimeControllerError("Runtime controller omitted its deployment identifier.")
    if state not in ALLOWED_RUNTIME_STATES:
        raise RuntimeControllerError("Runtime controller returned an invalid state.")
    if not isinstance(message, str):
        raise RuntimeControllerError("Runtime controller returned an invalid status message.")
    message = " ".join(message.split())[:500]
    if (
        not isinstance(observed_generation, int)
        or isinstance(observed_generation, bool)
        or observed_generation < 0
    ):
        raise RuntimeControllerError(
            "Runtime controller returned an invalid observed generation."
        )
    if not isinstance(components, list) or len(components) > 100:
        raise RuntimeControllerError("Runtime controller returned invalid components.")
    validated_components = tuple(_component_snapshot(component) for component in components)
    return RuntimeSnapshot(
        controller_id=controller_id,
        state=state,
        message=message,
        observed_generation=observed_generation,
        components=validated_components,
    )


def _component_snapshot(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeControllerError("Runtime controller returned invalid components.")
    required = {
        "slug",
        "image_digest",
        "desired_replicas",
        "ready_replicas",
        "available_replicas",
        "state",
        "health",
        "restart_count",
    }
    if not required <= set(value):
        raise RuntimeControllerError("Runtime controller returned invalid components.")
    slug = value["slug"]
    image_digest = value["image_digest"]
    state = value["state"]
    health = value["health"]
    last_error = value.get("last_error", "")
    counts = [
        value["desired_replicas"],
        value["ready_replicas"],
        value["available_replicas"],
        value["restart_count"],
    ]
    if (
        not isinstance(slug, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", slug)
        or not isinstance(image_digest, str)
        or len(image_digest) > 255
        or not isinstance(state, str)
        or len(state) > 32
        or not isinstance(health, str)
        or len(health) > 32
        or not isinstance(last_error, str)
        or any(
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > 100_000
            for count in counts
        )
    ):
        raise RuntimeControllerError("Runtime controller returned invalid components.")
    return {
        "slug": slug,
        "image_digest": image_digest,
        "desired_replicas": counts[0],
        "ready_replicas": counts[1],
        "available_replicas": counts[2],
        "state": " ".join(state.split())[:32],
        "health": " ".join(health.split())[:32],
        "restart_count": counts[3],
        "last_error": " ".join(last_error.split())[:500],
    }
