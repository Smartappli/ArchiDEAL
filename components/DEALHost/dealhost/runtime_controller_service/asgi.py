from __future__ import annotations

import hmac
import json
import logging
import re
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs

from .config import ControllerConfigurationError, ControllerSettings
from .contract import (
    ContractError,
    parse_desired_deployment,
    validate_deployment_id,
    validate_request_id,
)
from .kubernetes import KubernetesApiError, KubernetesClient
from .service import RuntimeReconciler


logger = logging.getLogger("dealhost.runtime_controller")

MAX_REQUEST_BYTES = 256 * 1024
_DEPLOYMENT_ROUTE = re.compile(r"^/v1/deployments/([^/]+)$")
_ACTION_ROUTE = re.compile(
    r"^/v1/deployments/([^/]+)/actions/(start|stop|restart|redeploy)$"
)
_LOG_ROUTE = re.compile(r"^/v1/deployments/([^/]+)/logs$")


class DuplicateJsonKey(ValueError):
    pass


class RuntimeControllerApplication:
    def __init__(
        self,
        settings: ControllerSettings,
        reconciler: RuntimeReconciler,
    ) -> None:
        self.settings = settings
        self.reconciler = reconciler

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope.get("type") != "http":
            return
        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        if method == "GET" and path == "/health/live":
            await _response(send, 200, {"status": "ok"})
            return
        if method == "GET" and path == "/health/ready":
            await self._ready(send)
            return

        try:
            headers = _headers(scope)
            self._authenticate(headers)
            request_id = validate_request_id(_required_header(headers, "idempotency-key"))
            result, status_code = await self._dispatch(
                method,
                path,
                scope.get("query_string", b""),
                headers,
                receive,
                request_id,
            )
            await _response(
                send,
                status_code,
                result,
                request_id=request_id,
            )
        except ContractError as exc:
            await _response(
                send,
                exc.status_code,
                {"detail": str(exc), "code": exc.code},
            )
        except KubernetesApiError as exc:
            logger.warning("Kubernetes reconciliation failed: %s", exc)
            await _response(
                send,
                503,
                {
                    "detail": "The Kubernetes runtime backend is unavailable.",
                    "code": "kubernetes_backend_unavailable",
                },
            )
        except Exception:
            logger.exception("Unexpected runtime-controller request failure")
            await _response(
                send,
                500,
                {
                    "detail": "The runtime controller failed unexpectedly.",
                    "code": "runtime_controller_error",
                },
            )

    async def _dispatch(
        self,
        method: str,
        path: str,
        query_string: bytes,
        headers: dict[str, str],
        receive,
        request_id: str,
    ) -> tuple[dict[str, Any], int]:
        if path == "/v1/deployments" and method == "POST":
            payload = await _json_body(headers, receive, required=True)
            desired = parse_desired_deployment(payload, self.settings)
            result = await self.reconciler.deploy(desired, request_id=request_id)
            return result.as_dict(), 201

        log_match = _LOG_ROUTE.fullmatch(path)
        if log_match and method == "GET":
            await _reject_body(receive)
            deployment_id = validate_deployment_id(log_match.group(1))
            query = _query(query_string)
            if set(query) != {"component", "tail", "since_seconds"}:
                raise ContractError(
                    "Log query parameters must be component, tail and since_seconds.",
                    status_code=400,
                )
            component = _one_query(query, "component")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", component):
                raise ContractError("The log component is invalid.", status_code=400)
            tail = _query_integer(query, "tail", minimum=1, maximum=1000)
            since_seconds = _query_integer(
                query,
                "since_seconds",
                minimum=1,
                maximum=604_800,
            )
            result = await self.reconciler.logs(
                deployment_id,
                component_slug=component,
                tail_lines=tail,
                since_seconds=since_seconds,
            )
            return result.as_dict(), 200

        action_match = _ACTION_ROUTE.fullmatch(path)
        if action_match and method == "POST":
            deployment_id = validate_deployment_id(action_match.group(1))
            payload = await _json_body(headers, receive, required=True)
            desired = parse_desired_deployment(payload, self.settings)
            if desired.deployment_id != deployment_id:
                raise ContractError(
                    "The payload deployment identifier does not match its path."
                )
            result = await self.reconciler.action(
                desired,
                action_match.group(2),
                request_id=request_id,
            )
            return result.as_dict(), 200

        deployment_match = _DEPLOYMENT_ROUTE.fullmatch(path)
        if deployment_match:
            deployment_id = validate_deployment_id(deployment_match.group(1))
            if method == "GET":
                await _reject_body(receive)
                result = await self.reconciler.observe(deployment_id)
                return result.as_dict(), 200
            if method == "PUT":
                payload = await _json_body(headers, receive, required=True)
                desired = parse_desired_deployment(payload, self.settings)
                if desired.deployment_id != deployment_id:
                    raise ContractError(
                        "The payload deployment identifier does not match its path."
                    )
                result = await self.reconciler.deploy(
                    desired,
                    request_id=request_id,
                    require_existing=True,
                )
                return result.as_dict(), 200
            if method == "DELETE":
                payload = await _json_body(headers, receive, required=False)
                desired = (
                    parse_desired_deployment(
                        payload,
                        self.settings,
                        allow_absent=True,
                    )
                    if payload is not None
                    else None
                )
                if desired is not None and desired.deployment_id != deployment_id:
                    raise ContractError(
                        "The DELETE payload deployment identifier does not match its path."
                    )
                result = await self.reconciler.undeploy(
                    deployment_id,
                    request_id=request_id,
                    desired=desired,
                )
                return result.as_dict(), 200

        await _reject_body(receive)
        raise ContractError(
            "The runtime-controller endpoint does not exist.",
            code="not_found",
            status_code=404,
        )

    def _authenticate(self, headers: dict[str, str]) -> None:
        authorization = headers.get("authorization", "")
        expected = f"Bearer {self.settings.auth_token}"
        if not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise ContractError(
                "Runtime-controller authentication failed.",
                code="authentication_failed",
                status_code=401,
            )

    async def _ready(self, send) -> None:
        try:
            self.settings.validate(require_files=True)
            token = self.settings.kubernetes_token_file.read_text(
                encoding="utf-8"
            ).strip()
            if not token:
                raise ControllerConfigurationError(
                    "The projected Kubernetes token is empty."
                )
        except (ControllerConfigurationError, OSError):
            await _response(send, 503, {"status": "unavailable"})
            return
        await _response(send, 200, {"status": "ready"})

    @staticmethod
    async def _lifespan(receive, send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


class LazyRuntimeControllerApplication:
    """Load mounted credentials only inside the controller process."""

    def __init__(self) -> None:
        self._application: RuntimeControllerApplication | None = None

    async def __call__(self, scope, receive, send) -> None:
        if self._application is None:
            settings = ControllerSettings.from_env()
            kubernetes = KubernetesClient(settings)
            self._application = RuntimeControllerApplication(
                settings,
                RuntimeReconciler(settings, kubernetes),
            )
        await self._application(scope, receive, send)


def create_application(
    settings: ControllerSettings,
    reconciler: RuntimeReconciler,
) -> RuntimeControllerApplication:
    return RuntimeControllerApplication(settings, reconciler)


def _headers(scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        try:
            name = raw_name.decode("ascii").lower()
            value = raw_value.decode("latin-1").strip()
        except UnicodeDecodeError as exc:
            raise ContractError("Request headers are invalid.", status_code=400) from exc
        if name in headers:
            raise ContractError("Duplicate request headers are not accepted.", status_code=400)
        headers[name] = value
    return headers


def _required_header(headers: dict[str, str], name: str) -> str:
    value = headers.get(name, "")
    if not value:
        raise ContractError(
            f"{name} is required.",
            code="missing_request_header",
            status_code=400,
        )
    return value


async def _body(receive) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        message_type = message.get("type")
        if message_type == "http.disconnect":
            raise ContractError("The request was disconnected.", status_code=400)
        if message_type != "http.request":
            raise ContractError("The HTTP request body is invalid.", status_code=400)
        chunk = message.get("body", b"")
        if not isinstance(chunk, bytes):
            raise ContractError("The HTTP request body is invalid.", status_code=400)
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            raise ContractError(
                "The runtime request body is too large.",
                code="request_too_large",
                status_code=413,
            )
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


async def _json_body(
    headers: dict[str, str],
    receive,
    *,
    required: bool,
) -> object | None:
    content = await _body(receive)
    if not content and not required:
        return None
    if not content:
        raise ContractError("A JSON request body is required.", status_code=400)
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ContractError("Content-Type must be application/json.", status_code=415)
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateJsonKey) as exc:
        raise ContractError("The JSON request body is malformed.", status_code=400) from exc


async def _reject_body(receive) -> None:
    if await _body(receive):
        raise ContractError("This endpoint does not accept a request body.", status_code=400)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(key)
        result[key] = value
    return result


def _query(value: bytes) -> dict[str, list[str]]:
    try:
        raw = value.decode("ascii")
        return parse_qs(
            raw,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=10,
            separator="&",
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise ContractError("The request query string is invalid.", status_code=400) from exc


def _one_query(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name)
    if not isinstance(values, list) or len(values) != 1 or not values[0]:
        raise ContractError(f"Query parameter {name} is invalid.", status_code=400)
    return values[0]


def _query_integer(
    query: dict[str, list[str]],
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _one_query(query, name)
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ContractError(f"Query parameter {name} is invalid.", status_code=400)
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ContractError(f"Query parameter {name} is out of range.", status_code=400)
    return parsed


async def _response(
    send,
    status: int,
    payload: dict[str, Any],
    *,
    request_id: str = "",
) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"cache-control", b"no-store"),
        (b"content-length", str(len(content)).encode("ascii")),
        (b"x-content-type-options", b"nosniff"),
    ]
    if request_id:
        headers.append((b"x-request-id", request_id.encode("ascii")))
    if status == 401:
        headers.append((b"www-authenticate", b'Bearer realm="runtime-controller"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": content})


application = LazyRuntimeControllerApplication()
