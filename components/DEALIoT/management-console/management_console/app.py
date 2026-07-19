from __future__ import annotations

import base64
import concurrent.futures
import hmac
import http.client
import ipaddress
import json
import logging
import os
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult, parse_qs, quote, unquote, urlencode, urlparse

from management_console import device_registry
from management_console.catalog import (
    COMPONENTS,
    catalog_payload,
    compliance_payload,
    cra_payload,
    data_act_payload,
    dataset_payload,
    dga_payload,
    dora_payload,
    intermediation_payload,
    legal_compliance_payload,
    nis2_payload,
    research_payload,
    security_resilience_payload,
)
from management_console.openaire import (
    OpenAIREExportError,
    export_dataset_to_openaire,
    openaire_export_payload,
)
from management_console.zenodo import (
    ZenodoExportError,
    export_dataset_to_zenodo,
    zenodo_export_payload,
)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_REQUEST_BYTES = 65536
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
PUBLIC_BASE_PATH = "/dealiot"
LOGGER = logging.getLogger("dealiot.management_console")
READINESS_COMPONENT_IDS = ("vernemq", "kafka")
OIDC_CONFIGURATION_NAMES = (
    "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL",
    "MANAGEMENT_CONSOLE_OIDC_ISSUER",
    "MANAGEMENT_CONSOLE_OIDC_AUDIENCE",
    "MANAGEMENT_CONSOLE_OIDC_CLIENT_ID",
    "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET",
    "MANAGEMENT_CONSOLE_OIDC_READ_ROLES",
    "MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES",
)
PUBLIC_ORIGIN_CONFIGURATION_NAME = "MANAGEMENT_CONSOLE_PUBLIC_ORIGIN"
DEFAULT_OIDC_GROUPS_CLAIM = "groups"
MAX_OIDC_CLAIM_LENGTH = 255
FORBIDDEN_OIDC_GROUPS_CLAIMS = frozenset(
    {
        "scope",
        "scp",
        "roles",
        "realm_access",
        "realm_access.roles",
    }
)


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    level: str | None


def management_console_token() -> str | None:
    value = os.getenv("MANAGEMENT_CONSOLE_TOKEN", "").strip()
    return value or None


def csv_env(name: str, default: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, default).split(",") if item.strip()}


def configured_oidc_groups_claim_name() -> str | None:
    configured = os.getenv(
        "MANAGEMENT_CONSOLE_OIDC_GROUPS_CLAIM",
        DEFAULT_OIDC_GROUPS_CLAIM,
    )
    claim_name = configured.strip()
    if (
        not claim_name
        or configured != claim_name
        or len(claim_name) > MAX_OIDC_CLAIM_LENGTH
        or "\0" in claim_name
        or claim_name.casefold() in FORBIDDEN_OIDC_GROUPS_CLAIMS
    ):
        return None
    return claim_name


def token_authorization_groups(claims: dict[str, Any]) -> set[str]:
    """Read authorization groups from exactly one configured top-level claim."""

    claim_name = configured_oidc_groups_claim_name()
    if claim_name is None:
        return set()
    groups = claims.get(claim_name)
    if not isinstance(groups, list):
        return set()
    if any(
        not isinstance(group, str) or not group.strip() or group != group.strip()
        for group in groups
    ):
        return set()
    return set(groups)


def introspect_oidc_token(token: str) -> dict[str, Any] | None:
    endpoint = os.getenv("MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL", "").strip()
    if not endpoint:
        return None

    client_id = os.getenv("MANAGEMENT_CONSOLE_OIDC_CLIENT_ID", "").strip()
    client_secret = os.getenv("MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        LOGGER.error("OIDC introspection is configured without client credentials")
        return {}

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
    body = urlencode({"token": token}).encode("ascii")
    try:
        response = open_http_request(
            "POST",
            endpoint,
            timeout=timeout_seconds(),
            body=body,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
    except (OSError, ValueError) as exc:
        LOGGER.warning("OIDC introspection failed: %s", exc)
        return {}

    if response.getcode() >= HTTPStatus.BAD_REQUEST:
        return {}
    try:
        claims = json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(claims, dict) or claims.get("active") is not True:
        return {}
    expected_issuer = os.getenv("MANAGEMENT_CONSOLE_OIDC_ISSUER", "").strip()
    if expected_issuer and claims.get("iss") != expected_issuer:
        return {}
    expected_audience = os.getenv("MANAGEMENT_CONSOLE_OIDC_AUDIENCE", "").strip()
    audience = claims.get("aud")
    if isinstance(audience, str):
        audiences = {audience}
    elif isinstance(audience, list):
        audiences = {str(value) for value in audience}
    else:
        audiences = set()
    if expected_audience and expected_audience not in audiences:
        return {}
    return claims


def bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return token or None


def authenticated_principal(authorization: str | None) -> Principal | None:
    token = bearer_token(authorization)
    if token is None:
        return None

    if os.getenv("MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL", "").strip():
        claims = introspect_oidc_token(token)
        if not claims:
            return None
        authorization_groups = token_authorization_groups(claims)
        write_groups = csv_env(
            "MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES",
            "dealiot-write,dealiot-admin",
        )
        read_groups = csv_env(
            "MANAGEMENT_CONSOLE_OIDC_READ_ROLES",
            "dealiot-read,dealiot-write,dealiot-admin",
        )
        level = None
        if authorization_groups & write_groups:
            level = "write"
        elif authorization_groups & read_groups:
            level = "read"
        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not subject
            or subject != subject.strip()
            or len(subject) > MAX_OIDC_CLAIM_LENGTH
            or "\x00" in subject
        ):
            LOGGER.warning("OIDC introspection response has no valid stable sub claim")
            return None
        return Principal(
            subject=subject,
            roles=frozenset(authorization_groups),
            level=level,
        )

    # The shared static credential is a local-development compatibility path only.
    # Keep this runtime guard as well as startup validation for alternate launchers.
    legacy_token = None if management_console_production_mode() else management_console_token()
    if legacy_token is not None and hmac.compare_digest(token, legacy_token):
        return Principal(
            subject="static-management-token",
            roles=frozenset({"dealiot-admin"}),
            level="write",
        )
    return None


def authorization_level(authorization: str | None) -> str | None:
    principal = authenticated_principal(authorization)
    return principal.level if principal is not None else None


def level_allows(actual: str | None, required: str) -> bool:
    levels = {"read": 1, "write": 2}
    return levels.get(actual or "", 0) >= levels.get(required, 99)


def bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in TRUTHY_ENV_VALUES


def management_console_production_mode() -> bool:
    """Return whether the console must enforce its production auth boundary."""
    return bool_env("MANAGEMENT_CONSOLE_PRODUCTION_MODE")


def management_console_auth_configured() -> bool:
    """Return whether bearer-token or OIDC authentication is configured."""
    return bool(
        management_console_token()
        or os.getenv("MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL", "").strip()
    )


def canonical_origin(value: str) -> str:
    """Return a normalized HTTP origin or reject values containing URL surface."""

    if not value or value != value.strip() or value == "null":
        raise ValueError("origin must be an absolute HTTP origin")
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("origin must contain only scheme, host and optional port")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("origin has an invalid port") from exc
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    rendered_host = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    port_suffix = f":{port}" if port is not None and port != default_port else ""
    return f"{scheme}://{rendered_host}{port_suffix}"


def configured_public_origin() -> str | None:
    value = os.getenv(PUBLIC_ORIGIN_CONFIGURATION_NAME, "").strip()
    return canonical_origin(value) if value else None


def validate_production_auth_config() -> None:
    """Reject an incomplete production identity boundary before serving traffic."""
    if not management_console_production_mode():
        return

    if management_console_token():
        raise RuntimeError(
            "MANAGEMENT_CONSOLE_TOKEN is not accepted in production; configure the "
            "OIDC introspection boundary instead",
        )

    oidc_values = {name: os.getenv(name, "").strip() for name in OIDC_CONFIGURATION_NAMES}
    required = {name: oidc_values[name] for name in OIDC_CONFIGURATION_NAMES}
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise RuntimeError(
            "Incomplete production authentication configuration: " + ", ".join(missing),
        )
    if configured_oidc_groups_claim_name() is None:
        raise RuntimeError(
            "MANAGEMENT_CONSOLE_OIDC_GROUPS_CLAIM must name a dedicated top-level "
            "group claim and must not be scope, scp, roles, realm_access, or "
            "realm_access.roles",
        )
    for name in (
        "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL",
        "MANAGEMENT_CONSOLE_OIDC_ISSUER",
    ):
        if not required[name].startswith("https://"):
            message = f"{name} must use HTTPS in production"
            raise RuntimeError(message)
    try:
        public_origin = configured_public_origin()
    except ValueError as exc:
        message = f"Invalid {PUBLIC_ORIGIN_CONFIGURATION_NAME}: {exc}"
        raise RuntimeError(message) from exc
    if public_origin is None:
        message = f"Incomplete production request boundary: {PUBLIC_ORIGIN_CONFIGURATION_NAME}"
        raise RuntimeError(message)
    if not public_origin.startswith("https://"):
        message = f"{PUBLIC_ORIGIN_CONFIGURATION_NAME} must use HTTPS in production"
        raise RuntimeError(message)


def is_wildcard_bind(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


def configured_bind_host() -> str:
    host = os.getenv("MANAGEMENT_CONSOLE_BIND", "127.0.0.1").strip() or "127.0.0.1"
    if is_wildcard_bind(host) and not bool_env("MANAGEMENT_CONSOLE_ALLOW_WILDCARD_BIND"):
        raise ValueError(
            "Wildcard bind requires MANAGEMENT_CONSOLE_ALLOW_WILDCARD_BIND=true",
        )
    return host


class SimpleHttpResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self.body


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def timeout_seconds() -> float:
    value = os.getenv("MANAGEMENT_CONSOLE_PROBE_TIMEOUT_SECONDS", "")
    if not value:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(0.2, min(float(value), 10.0))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def http_path(parsed_url: ParseResult) -> str:
    path = parsed_url.path or "/"
    if parsed_url.params:
        path = f"{path};{parsed_url.params}"
    if parsed_url.query:
        return f"{path}?{parsed_url.query}"
    return path


def parse_http_url(url: str) -> ParseResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("HTTP request URL must use http or https with a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("HTTP request URL must not include credentials")
    if parsed.fragment:
        raise ValueError("HTTP request URL must not include a fragment")
    return parsed


def open_http_request(
    method: str,
    url: str,
    timeout: float,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> SimpleHttpResponse:
    parsed = parse_http_url(url)

    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    host = parsed.hostname
    if host is None:
        raise ValueError("HTTP request URL must use http or https with a host")
    connection = connection_cls(host, port=parsed.port, timeout=timeout)
    try:
        connection.request(method, http_path(parsed), body=body, headers=headers or {})
        response = connection.getresponse()
        return SimpleHttpResponse(response.status, response.read())
    finally:
        connection.close()


def probe_tcp(endpoint: str, timeout: float) -> dict[str, Any]:
    parsed = urlparse(endpoint)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        return {"status": "unknown", "detail": "invalid tcp probe"}

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"status": "healthy", "detail": f"tcp:{host}:{port}"}
    except OSError as exc:
        return {"status": "unreachable", "detail": str(exc)}


def probe_http(endpoint: str, timeout: float) -> dict[str, Any]:
    try:
        parse_http_url(endpoint)
    except ValueError:
        return {"status": "unknown", "detail": "invalid http probe scheme"}

    try:
        status = open_http_request("GET", endpoint, timeout=timeout).getcode()
    except OSError as exc:
        return {"status": "unreachable", "detail": str(exc)}
    else:
        if status < HTTPStatus.INTERNAL_SERVER_ERROR:
            return {"status": "healthy", "detail": f"http {status}"}
        return {"status": "degraded", "detail": f"http {status}"}


def first_host_port(value: str) -> str | None:
    first = next((item.strip() for item in value.split(",") if item.strip()), "")
    if not first:
        return None
    return first.removeprefix("PLAINTEXT://").removeprefix("SSL://").removeprefix("SASL_SSL://")


def endpoint_with_path(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def internal_request_path(path: str) -> str:
    """Map the unified public prefix to the console's internal route space."""
    request_path = urlparse(path).path
    if request_path == PUBLIC_BASE_PATH:
        return "/"
    if request_path.startswith(f"{PUBLIC_BASE_PATH}/"):
        return request_path.removeprefix(PUBLIC_BASE_PATH)
    return request_path


def mqtt_probe() -> str | None:
    mqtt_host = os.getenv("MQTT_HOST")
    mqtt_port = os.getenv("MQTT_PORT", "1883")
    if mqtt_host:
        return f"tcp://{mqtt_host}:{mqtt_port}"
    return None


def kafka_probe() -> str | None:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if not bootstrap:
        return None
    host_port = first_host_port(bootstrap)
    if not host_port:
        return None
    return f"tcp://{host_port}"


def apicurio_probe() -> str | None:
    health_url = os.getenv("APICURIO_REGISTRY_HEALTH_URL")
    if health_url:
        return health_url
    registry_url = os.getenv("APICURIO_REGISTRY_URL") or os.getenv("APICURIO_REGISTRY_V3_URL")
    if registry_url:
        return endpoint_with_path(registry_url, "system/info")
    return None


def endpoint_probe(env_name: str, path: str | None = None) -> str | None:
    value = os.getenv(env_name)
    if not value:
        return None
    if path is None:
        return value
    return endpoint_with_path(value, path)


PROBE_OVERRIDES = {
    "vernemq": mqtt_probe,
    "mqtt-kafka-bridge": lambda: endpoint_probe("MQTT_KAFKA_BRIDGE_HEALTH_URL"),
    "kafka": kafka_probe,
    "apicurio": apicurio_probe,
    "seaweedfs": lambda: endpoint_probe("S3_ENDPOINT_URL"),
    "flink": lambda: endpoint_probe("FLINK_REST_URL", "overview"),
    "airflow": lambda: endpoint_probe("AIRFLOW_API_URL", "version"),
    "prometheus": lambda: endpoint_probe("PROMETHEUS_URL", "-/ready"),
    "grafana": lambda: endpoint_probe("GRAFANA_URL", "api/health"),
}


def configured_probe(component: dict[str, Any]) -> str | None:
    override = PROBE_OVERRIDES.get(component["id"])
    if override is not None:
        endpoint = override()
        if endpoint:
            return endpoint
    return component.get("probe")


def probe_component(component: dict[str, Any]) -> dict[str, Any]:
    endpoint = configured_probe(component)
    if not endpoint:
        return {
            "id": component["id"],
            "status": "unknown",
            "detail": "no probe configured",
            "checked_at": now_iso(),
        }

    timeout = timeout_seconds()
    if endpoint.startswith("tcp://"):
        result = probe_tcp(endpoint, timeout)
    else:
        result = probe_http(endpoint, timeout)

    return {
        "id": component["id"],
        "status": result["status"],
        "detail": result["detail"],
        "checked_at": now_iso(),
    }


def configured_component_ids(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def components_for_ids(component_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    components_by_id = {component["id"]: component for component in COMPONENTS}
    return [
        components_by_id.get(component_id, {"id": component_id, "probe": None})
        for component_id in component_ids
    ]


def probe_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not components:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(components)) as executor:
        return list(executor.map(probe_component, components))


def status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    return counts


def required_component_checks(component_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    if component_ids:
        return probe_components(components_for_ids(component_ids))
    return [
        {
            "id": "management-console-health-scope",
            "status": "unknown",
            "detail": "MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS must not be empty",
            "checked_at": now_iso(),
        }
    ]


def health_payload() -> dict[str, Any]:
    catalog_ids = tuple(component["id"] for component in COMPONENTS)
    required_ids = configured_component_ids(
        "MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS",
        catalog_ids,
    )
    optional_ids = tuple(
        component_id
        for component_id in configured_component_ids(
            "MANAGEMENT_CONSOLE_OPTIONAL_COMPONENT_IDS",
            (),
        )
        if component_id not in required_ids
    )
    required_checks = required_component_checks(required_ids)
    optional_checks = probe_components(components_for_ids(optional_ids))
    selected_ids = set(required_ids) | set(optional_ids)

    return {
        "checked_at": now_iso(),
        # Keep the existing top-level contract focused on required dependencies so
        # clients do not mistake an unavailable optional subsystem for a module outage.
        "summary": status_counts(required_checks),
        "checks": required_checks,
        "optional_summary": status_counts(optional_checks),
        "optional_checks": optional_checks,
        "scope": {
            "required": list(required_ids),
            "optional": list(optional_ids),
            "excluded": [
                component_id for component_id in catalog_ids if component_id not in selected_ids
            ],
        },
    }


def readiness_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    component_ids = configured_component_ids(
        "MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS",
        READINESS_COMPONENT_IDS,
    )
    checks = required_component_checks(component_ids)
    required_ids = list(component_ids)
    registry_required = (
        device_registry.database_is_configured() or management_console_production_mode()
    )
    if registry_required:
        registry_check = {
            "id": "dealiot-registry",
            "status": "healthy",
            "detail": "postgresql schema current",
            "checked_at": now_iso(),
        }
        try:
            device_registry.check_readiness()
        except device_registry.RegistryUnavailableError:
            registry_check.update(
                status="unreachable",
                detail="registry database or schema unavailable",
            )
        checks.append(registry_check)
        required_ids.append("dealiot-registry")
    ready = (
        bool(required_ids)
        and len(checks) == len(required_ids)
        and all(check["status"] == "healthy" for check in checks)
    )
    status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
    return status, {
        "status": "ready" if ready else "not_ready",
        "checked_at": now_iso(),
        "checks": checks,
        "scope": {"required": required_ids},
    }


def airflow_auth_header() -> str | None:
    username = os.getenv("AIRFLOW_API_USERNAME")
    password = os.getenv("AIRFLOW_API_PASSWORD")
    if not username or not password:
        return None
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def trigger_media_backfill(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    auth_header = airflow_auth_header()
    if auth_header is None:
        return (
            HTTPStatus.CONFLICT,
            {
                "error": "missing_airflow_credentials",
                "message": "Set AIRFLOW_API_USERNAME and AIRFLOW_API_PASSWORD for this action.",
            },
        )

    airflow_api_url = os.getenv("AIRFLOW_API_URL", "http://airflow-apiserver:8080/api/v2")
    dag_run_url = f"{airflow_api_url.rstrip('/')}/dags/media_backfill/dagRuns"
    try:
        parse_http_url(dag_run_url)
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_airflow_api_url"}

    body = json.dumps(
        {
            "dag_run_id": payload.get("dag_run_id") or f"manual__management_console__{now_iso()}",
            "conf": payload.get("conf", {}),
        }
    ).encode("utf-8")

    try:
        response = open_http_request(
            "POST",
            dag_run_url,
            timeout=timeout_seconds(),
            body=body,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    except OSError as exc:
        return HTTPStatus.BAD_GATEWAY, {"error": "airflow_unreachable", "detail": str(exc)}

    response_body = response.read().decode("utf-8", errors="replace")
    if response.getcode() >= HTTPStatus.BAD_REQUEST:
        return response.getcode(), {"error": "airflow_rejected_request", "detail": response_body}
    parsed = json.loads(response_body) if response_body else {}
    return response.getcode(), {"status": "submitted", "airflow_response": parsed}


def read_json_body(handler: Any) -> dict[str, Any]:
    raw_length = handler.headers.get("Content-Length", "0") or "0"
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("Content-Length must be a non-negative integer") from exc
    if length < 0:
        raise ValueError("Content-Length must be a non-negative integer")
    if length > MAX_REQUEST_BYTES:
        raise ValueError("request body too large")
    if length == 0:
        return {}
    body = handler.rfile.read(length)
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("request body must be a JSON object")
    return cast("dict[str, Any]", parsed)


def device_identifier_from_path(path: str) -> str | None:
    prefix = "/api/devices/"
    if not path.startswith(prefix):
        return None
    return device_registry.validate_device_id(unquote(path.removeprefix(prefix)))


def etag_for_revision(revision: int) -> str:
    return f'"{revision}"'


def revision_from_if_match(value: str | None) -> int:
    if value is None:
        raise DevicePreconditionRequiredError
    match = re.fullmatch(r'"([1-9][0-9]*)"', value.strip())
    if match is None:
        raise device_registry.DeviceValidationError(
            'If-Match must contain a device ETag such as "3"',
        )
    return int(match.group(1))


class DevicePreconditionRequiredError(Exception):
    """A conditional device mutation omitted its If-Match header."""


class ManagementConsoleHandler(BaseHTTPRequestHandler):
    server_version = "DEALIoTManagementConsole/1.0"
    sys_version = ""

    def send_security_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
            "object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'",
        )
        self.send_header(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if management_console_production_mode():
            self.send_header(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

    def resolve_principal(self) -> Principal | None:
        if not management_console_auth_configured():
            if management_console_production_mode():
                return None
            return Principal(
                subject="development-user",
                roles=frozenset({"dealiot-admin"}),
                level="write",
            )
        return authenticated_principal(self.headers.get("Authorization"))

    def request_authorized(self, required_level: str = "read") -> bool:
        principal = self.resolve_principal()
        return principal is not None and level_allows(principal.level, required_level)

    def discard_request_body(self) -> None:
        if self.headers.get("Transfer-Encoding") is not None:
            # BaseHTTPRequestHandler does not decode chunked request bodies. Closing is
            # required so unconsumed chunks cannot be parsed as a pipelined request.
            self.close_connection = True
            return
        raw_length = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            self.close_connection = True
            return
        if length < 0:
            self.close_connection = True
            return
        if length > 0:
            self.rfile.read(min(length, MAX_REQUEST_BYTES + 1))
        if length > MAX_REQUEST_BYTES:
            self.close_connection = True

    def header_values(self, name: str) -> list[str]:
        get_all = getattr(self.headers, "get_all", None)
        if callable(get_all):
            return [str(value) for value in (get_all(name) or [])]
        value = self.headers.get(name)
        return [str(value)] if value is not None else []

    def inferred_development_origin(self) -> str | None:
        """Infer a local same-origin boundary when the explicit setting is absent."""

        host_values = self.header_values("Host")
        forwarded_proto_values = self.header_values("X-Forwarded-Proto")
        if len(host_values) != 1 or len(forwarded_proto_values) > 1:
            return None
        scheme = forwarded_proto_values[0].strip().lower() if forwarded_proto_values else "http"
        if "," in scheme:
            return None
        try:
            return canonical_origin(f"{scheme}://{host_values[0]}")
        except ValueError:
            return None

    def mutation_origin_allowed(self) -> bool:
        origins = self.header_values("Origin")
        if not origins:
            # Bearer-authenticated CLI and service clients do not send Origin.
            return True
        if len(origins) != 1:
            return False
        try:
            actual = canonical_origin(origins[0])
            expected = configured_public_origin()
        except ValueError:
            return False
        if expected is None:
            if management_console_production_mode():
                return False
            expected = self.inferred_development_origin()
        return expected is not None and hmac.compare_digest(actual, expected)

    def json_content_type_valid(self) -> bool:
        content_types = self.header_values("Content-Type")
        if len(content_types) != 1:
            return False
        media_type = content_types[0].split(";", 1)[0].strip().casefold()
        return media_type == "application/json"

    def request_body_is_empty(self) -> bool:
        if self.header_values("Transfer-Encoding"):
            return False
        content_lengths = self.header_values("Content-Length")
        if not content_lengths:
            return True
        if len(content_lengths) != 1:
            return False
        try:
            return int(content_lengths[0]) == 0
        except ValueError:
            return False

    def require_mutation_boundary(self, *, json_body: bool) -> bool:
        if not self.mutation_origin_allowed():
            self.discard_request_body()
            self.respond_json(
                {"error": "cross_origin_mutation_forbidden"},
                status=HTTPStatus.FORBIDDEN,
            )
            return False
        if self.header_values("Transfer-Encoding"):
            self.discard_request_body()
            self.respond_json(
                {"error": "transfer_encoding_not_supported"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return False
        if json_body and not self.json_content_type_valid():
            self.discard_request_body()
            self.respond_json(
                {"error": "application_json_required"},
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return False
        return True

    def require_authorization(
        self,
        *,
        required_level: str = "read",
        discard_body: bool = False,
    ) -> bool:
        principal = self.resolve_principal()
        if principal is not None and level_allows(principal.level, required_level):
            self._principal = principal
            return True
        if discard_body:
            self.discard_request_body()
        if principal is None:
            self.respond_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
        else:
            self.respond_json({"error": "forbidden"}, status=HTTPStatus.FORBIDDEN)
        return False

    def principal_subject(self) -> str:
        principal = getattr(self, "_principal", None)
        if principal is None:
            raise RuntimeError("authorization must be evaluated before accessing the principal")
        return str(principal.subject)

    def respond_registry_error(self, exc: Exception) -> None:
        if isinstance(exc, device_registry.DeviceValidationError):
            status, code = HTTPStatus.BAD_REQUEST, "invalid_device_request"
        elif isinstance(exc, device_registry.DeviceNotFoundError):
            status, code = HTTPStatus.NOT_FOUND, "device_not_found"
        elif isinstance(exc, device_registry.DeviceConflictError):
            status, code = HTTPStatus.CONFLICT, "device_conflict"
        elif isinstance(exc, device_registry.RevisionConflictError):
            status, code = HTTPStatus.PRECONDITION_FAILED, "device_revision_conflict"
        elif isinstance(exc, DevicePreconditionRequiredError):
            status, code = HTTPStatus.PRECONDITION_REQUIRED, "if_match_required"
        else:
            status, code = HTTPStatus.SERVICE_UNAVAILABLE, "device_registry_unavailable"
        payload = {"error": code}
        if not isinstance(exc, device_registry.RegistryUnavailableError):
            payload["detail"] = str(exc)
        self.respond_json(payload, status=status)

    def respond_device_list(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        try:
            raw_limit = query.get("limit", ["50"])[0]
            limit = int(raw_limit)
            payload = device_registry.list_devices(
                status=query.get("status", [None])[0],
                kind=query.get("kind", [None])[0],
                query=query.get("q", [None])[0],
                limit=limit,
                cursor=query.get("cursor", [None])[0],
            )
        except (ValueError, device_registry.DeviceRegistryError) as exc:
            if isinstance(exc, ValueError):
                exc = device_registry.DeviceValidationError("limit must be an integer")
            self.respond_registry_error(exc)
            return
        self.respond_json(payload)

    def respond_device_detail(self, device_id: str) -> None:
        try:
            device = device_registry.get_device(device_id)
        except device_registry.DeviceRegistryError as exc:
            self.respond_registry_error(exc)
            return
        self.respond_json(
            {"device": device},
            headers={"ETag": etag_for_revision(int(device["revision"]))},
        )

    def do_GET(self) -> None:
        path = internal_request_path(self.path)
        requires_authorization = path.startswith("/api/") or (
            management_console_production_mode() and path not in {"/healthz", "/readyz"}
        )
        if requires_authorization and not self.require_authorization():
            return

        if path == "/api/devices":
            self.respond_device_list()
            return
        if path.startswith("/api/devices/"):
            try:
                device_id = device_identifier_from_path(path)
            except device_registry.DeviceValidationError as exc:
                self.respond_registry_error(exc)
                return
            if device_id is not None:
                self.respond_device_detail(device_id)
                return

        routes = {
            "/api/architecture": lambda: self.respond_json(catalog_payload()),
            "/api/compliance": lambda: self.respond_json(compliance_payload()),
            "/api/cra": lambda: self.respond_json(cra_payload()),
            "/api/data-act": lambda: self.respond_json(data_act_payload()),
            "/api/datasets": lambda: self.respond_json(dataset_payload()),
            "/api/datasets/openaire": lambda: self.respond_json(openaire_export_payload()),
            "/api/datasets/zenodo": lambda: self.respond_json(zenodo_export_payload()),
            "/api/dga": lambda: self.respond_json(dga_payload()),
            "/api/dora": lambda: self.respond_json(dora_payload()),
            "/api/health": lambda: self.respond_json(health_payload()),
            "/api/intermediation": lambda: self.respond_json(intermediation_payload()),
            "/api/legal-compliance": lambda: self.respond_json(legal_compliance_payload()),
            "/api/nis2": lambda: self.respond_json(nis2_payload()),
            "/api/research": lambda: self.respond_json(research_payload()),
            "/api/runbooks": lambda: self.respond_json({"runbooks": catalog_payload()["runbooks"]}),
            "/api/security-resilience": lambda: self.respond_json(security_resilience_payload()),
            "/healthz": lambda: self.respond_json({"status": "ok", "checked_at": now_iso()}),
            "/readyz": self.respond_readiness,
        }
        route = routes.get(path)
        if route is not None:
            route()
            return

        self.serve_static()

    def do_POST(self) -> None:
        if not self.require_authorization(required_level="write", discard_body=True):
            return
        if not self.require_mutation_boundary(json_body=True):
            return

        path = internal_request_path(self.path)
        if path == "/api/devices":
            try:
                payload = read_json_body(self)
                device = device_registry.create_device(payload, self.principal_subject())
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self.respond_registry_error(device_registry.DeviceValidationError(str(exc)))
                return
            except device_registry.DeviceRegistryError as exc:
                self.respond_registry_error(exc)
                return
            device_id = str(device["device_id"])
            self.respond_json(
                {"device": device},
                status=HTTPStatus.CREATED,
                headers={
                    "ETag": etag_for_revision(int(device["revision"])),
                    "Location": f"{PUBLIC_BASE_PATH}/api/devices/{quote(device_id, safe='')}",
                },
            )
            return

        actions = {
            "/api/operations/trigger-media-backfill": trigger_media_backfill,
            "/api/datasets/openaire/export": lambda payload: (
                HTTPStatus.CREATED,
                export_dataset_to_openaire(payload),
            ),
            "/api/datasets/zenodo/export": lambda payload: (
                HTTPStatus.CREATED,
                export_dataset_to_zenodo(payload),
            ),
        }
        action = actions.get(path)
        if action is None:
            self.respond_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = read_json_body(self)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self.respond_json(
                {"error": "invalid_request", "detail": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            status, response_payload = action(payload)
        except (OpenAIREExportError, ZenodoExportError) as exc:
            self.respond_json(
                {"error": exc.error_code, "detail": exc.detail},
                status=exc.status,
            )
            return

        self.respond_json(response_payload, status=status)

    def do_PATCH(self) -> None:
        if not self.require_authorization(required_level="write", discard_body=True):
            return
        if not self.require_mutation_boundary(json_body=True):
            return
        path = internal_request_path(self.path)
        try:
            device_id = device_identifier_from_path(path)
        except device_registry.DeviceValidationError as exc:
            self.respond_registry_error(exc)
            return
        if device_id is None:
            self.respond_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            revision = revision_from_if_match(self.headers.get("If-Match"))
            payload = read_json_body(self)
            device = device_registry.update_device(
                device_id,
                payload,
                self.principal_subject(),
                revision,
            )
        except DevicePreconditionRequiredError as exc:
            self.respond_registry_error(exc)
            return
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self.respond_registry_error(device_registry.DeviceValidationError(str(exc)))
            return
        except device_registry.DeviceRegistryError as exc:
            self.respond_registry_error(exc)
            return
        self.respond_json(
            {"device": device},
            headers={"ETag": etag_for_revision(int(device["revision"]))},
        )

    def do_DELETE(self) -> None:
        if not self.require_authorization(required_level="write", discard_body=True):
            return
        if not self.require_mutation_boundary(json_body=False):
            return
        if not self.request_body_is_empty():
            self.discard_request_body()
            self.respond_json(
                {"error": "request_body_not_allowed"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        path = internal_request_path(self.path)
        try:
            device_id = device_identifier_from_path(path)
        except device_registry.DeviceValidationError as exc:
            self.respond_registry_error(exc)
            return
        if device_id is None:
            self.respond_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            revision = revision_from_if_match(self.headers.get("If-Match"))
            next_revision = device_registry.retire_device(
                device_id,
                self.principal_subject(),
                revision,
            )
        except (DevicePreconditionRequiredError, device_registry.DeviceRegistryError) as exc:
            self.respond_registry_error(exc)
            return
        self.respond_empty(
            status=HTTPStatus.NO_CONTENT,
            headers={"ETag": etag_for_revision(next_revision)},
        )

    def respond_readiness(self) -> None:
        status, payload = readiness_payload()
        self.respond_json(payload, status=status)

    def serve_static(self) -> None:
        path = internal_request_path(self.path)
        relative_path = "index.html" if path in {"/", ""} else path.lstrip("/")
        target = (STATIC_DIR / relative_path).resolve()
        if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
            self.respond_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")

        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(content)

    def respond_json(
        self,
        payload: dict[str, Any],
        status: int = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(content)

    def respond_empty(
        self,
        status: int = HTTPStatus.NO_CONTENT,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_security_headers()
        self.end_headers()

    def log_message(  # pylint: disable=arguments-differ
        self,
        message_format: str,
        *args: Any,
    ) -> None:
        print(
            json.dumps(
                {
                    "time": now_iso(),
                    "client": self.client_address[0],
                    "message": message_format % args,
                },
                separators=(",", ":"),
            )
        )


def run() -> None:
    validate_production_auth_config()
    host = configured_bind_host()
    port = int(os.getenv("MANAGEMENT_CONSOLE_PORT", "8080"))
    with ThreadingHTTPServer((host, port), ManagementConsoleHandler) as server:
        print(f"management-console listening on {host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    run()
