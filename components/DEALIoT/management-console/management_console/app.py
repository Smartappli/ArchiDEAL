from __future__ import annotations

import base64
import concurrent.futures
import hmac
import http.client
import ipaddress
import json
import logging
import os
import socket
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult, urlencode, urlparse

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


def management_console_token() -> str | None:
    value = os.getenv("MANAGEMENT_CONSOLE_TOKEN", "").strip()
    return value or None


def csv_env(name: str, default: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, default).split(",") if item.strip()}


def token_roles(claims: dict[str, Any]) -> set[str]:
    roles = set(claims.get("roles", [])) if isinstance(claims.get("roles"), list) else set()
    groups = claims.get("groups")
    if isinstance(groups, list):
        roles.update(str(group) for group in groups)
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
        roles.update(str(role) for role in realm_access["roles"])
    scope = claims.get("scope")
    if isinstance(scope, str):
        roles.update(scope.split())
    return {str(role) for role in roles}


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


def authorization_level(authorization: str | None) -> str | None:
    token = bearer_token(authorization)
    if token is None:
        return None

    if os.getenv("MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL", "").strip():
        claims = introspect_oidc_token(token) or {}
        roles = token_roles(claims)
        write_roles = csv_env(
            "MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES",
            "dealiot-write,dealiot-admin",
        )
        read_roles = csv_env(
            "MANAGEMENT_CONSOLE_OIDC_READ_ROLES",
            "dealiot-read,dealiot-write,dealiot-admin",
        )
        if roles & write_roles:
            return "write"
        if roles & read_roles:
            return "read"
        return None

    legacy_token = management_console_token()
    if legacy_token is not None and hmac.compare_digest(token, legacy_token):
        return "write"
    return None


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


def validate_production_auth_config() -> None:
    """Reject an incomplete production identity boundary before serving traffic."""
    if not management_console_production_mode():
        return
    if management_console_token():
        return

    required = {
        "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL",
            "",
        ).strip(),
        "MANAGEMENT_CONSOLE_OIDC_ISSUER": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_ISSUER",
            "",
        ).strip(),
        "MANAGEMENT_CONSOLE_OIDC_AUDIENCE": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_AUDIENCE",
            "",
        ).strip(),
        "MANAGEMENT_CONSOLE_OIDC_CLIENT_ID": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_ID",
            "",
        ).strip(),
        "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET",
            "",
        ).strip(),
        "MANAGEMENT_CONSOLE_OIDC_READ_ROLES": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_READ_ROLES",
            "",
        ).strip(),
        "MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES": os.getenv(
            "MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES",
            "",
        ).strip(),
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise RuntimeError(
            "Incomplete production authentication configuration: " + ", ".join(missing),
        )
    for name in (
        "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL",
        "MANAGEMENT_CONSOLE_OIDC_ISSUER",
    ):
        if not required[name].startswith("https://"):
            message = f"{name} must use HTTPS in production"
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
    ready = (
        bool(component_ids)
        and len(checks) == len(component_ids)
        and all(check["status"] == "healthy" for check in checks)
    )
    status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
    return status, {
        "status": "ready" if ready else "not_ready",
        "checked_at": now_iso(),
        "checks": checks,
        "scope": {"required": list(component_ids)},
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
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length > MAX_REQUEST_BYTES:
        raise ValueError("request body too large")
    if length == 0:
        return {}
    body = handler.rfile.read(length)
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("request body must be a JSON object")
    return cast("dict[str, Any]", parsed)


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

    def request_authorized(self, required_level: str = "read") -> bool:
        if not management_console_auth_configured():
            return not management_console_production_mode()
        level = authorization_level(self.headers.get("Authorization"))
        return level == "write" or (level == "read" and required_level == "read")

    def discard_request_body(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 0:
            self.rfile.read(min(length, MAX_REQUEST_BYTES + 1))

    def require_authorization(
        self,
        *,
        required_level: str = "read",
        discard_body: bool = False,
    ) -> bool:
        if self.request_authorized(required_level):
            return True
        if discard_body:
            self.discard_request_body()
        self.respond_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
        return False

    def do_GET(self) -> None:
        path = internal_request_path(self.path)
        requires_authorization = path.startswith("/api/") or (
            management_console_production_mode() and path not in {"/healthz", "/readyz"}
        )
        if requires_authorization and not self.require_authorization():
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
        action = actions.get(internal_request_path(self.path))
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

    def respond_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(content)

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
