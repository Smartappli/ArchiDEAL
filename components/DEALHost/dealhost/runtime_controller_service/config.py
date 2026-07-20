from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PLACEHOLDERS = {"", "replace-me", "<runtime_controller_token>"}


class ControllerConfigurationError(RuntimeError):
    """Raised when the controller cannot start safely."""


@dataclass(frozen=True)
class ControllerSettings:
    auth_token: str
    environment: str
    namespace: str
    kubernetes_url: str
    kubernetes_token_file: Path
    kubernetes_ca_file: Path
    allowed_image_prefixes: tuple[str, ...]
    workload_service_account: str
    image_pull_secret: str
    secret_name_prefix: str
    secret_catalog_name: str
    secret_catalog_namespace: str
    max_replicas: int = 10
    request_timeout_seconds: float = 15.0
    lease_duration_seconds: int = 30
    lease_acquire_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> ControllerSettings:
        service_account_root = Path(
            os.getenv(
                "RUNTIME_CONTROLLER_SERVICE_ACCOUNT_ROOT",
                "/var/run/secrets/kubernetes.io/serviceaccount",
            )
        )
        namespace_file = service_account_root / "namespace"
        configured_namespace = os.getenv("RUNTIME_CONTROLLER_NAMESPACE", "").strip()
        if configured_namespace:
            namespace = configured_namespace
        else:
            try:
                namespace = namespace_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ControllerConfigurationError(
                    "RUNTIME_CONTROLLER_NAMESPACE or the mounted service-account namespace is required."
                ) from exc

        host = os.getenv("KUBERNETES_SERVICE_HOST", "").strip()
        port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443").strip()
        default_url = f"https://{host}:{port}" if host else ""
        kubernetes_url = (
            os.getenv("RUNTIME_CONTROLLER_KUBERNETES_URL", default_url)
            .strip()
            .rstrip("/")
        )

        prefixes = tuple(
            item.strip()
            for item in os.getenv(
                "RUNTIME_CONTROLLER_ALLOWED_IMAGE_PREFIXES",
                "ghcr.io/smartappli/",
            ).split(",")
            if item.strip()
        )
        try:
            maximum = int(os.getenv("RUNTIME_CONTROLLER_MAX_REPLICAS", "10"))
            timeout = float(
                os.getenv("RUNTIME_CONTROLLER_KUBERNETES_TIMEOUT_SECONDS", "15")
            )
            lease_duration = int(
                os.getenv("RUNTIME_CONTROLLER_LEASE_DURATION_SECONDS", "30")
            )
            lease_acquire_timeout = float(
                os.getenv(
                    "RUNTIME_CONTROLLER_LEASE_ACQUIRE_TIMEOUT_SECONDS",
                    "10",
                )
            )
        except ValueError as exc:
            raise ControllerConfigurationError(
                "Runtime-controller numeric settings are invalid."
            ) from exc

        settings = cls(
            auth_token=os.getenv("RUNTIME_CONTROLLER_AUTH_TOKEN", "").strip(),
            environment=os.getenv(
                "RUNTIME_CONTROLLER_ENVIRONMENT", "production"
            ).strip(),
            namespace=namespace,
            kubernetes_url=kubernetes_url,
            kubernetes_token_file=Path(
                os.getenv(
                    "RUNTIME_CONTROLLER_KUBERNETES_TOKEN_FILE",
                    str(service_account_root / "token"),
                )
            ),
            kubernetes_ca_file=Path(
                os.getenv(
                    "RUNTIME_CONTROLLER_KUBERNETES_CA_FILE",
                    str(service_account_root / "ca.crt"),
                )
            ),
            allowed_image_prefixes=prefixes,
            workload_service_account=os.getenv(
                "RUNTIME_CONTROLLER_WORKLOAD_SERVICE_ACCOUNT",
                "dealhost-runtime-application",
            ).strip(),
            image_pull_secret=os.getenv(
                "RUNTIME_CONTROLLER_IMAGE_PULL_SECRET",
                "archideal-registry-credentials",
            ).strip(),
            secret_name_prefix=os.getenv(
                "RUNTIME_CONTROLLER_SECRET_NAME_PREFIX",
                "dealapp",
            ).strip(),
            secret_catalog_name=os.getenv(
                "RUNTIME_CONTROLLER_SECRET_CATALOG_NAME",
                "dealhost-runtime-secret-catalog",
            ).strip(),
            secret_catalog_namespace=os.getenv(
                "RUNTIME_CONTROLLER_SECRET_CATALOG_NAMESPACE",
                "archideal",
            ).strip(),
            max_replicas=maximum,
            request_timeout_seconds=timeout,
            lease_duration_seconds=lease_duration,
            lease_acquire_timeout_seconds=lease_acquire_timeout,
        )
        settings.validate()
        return settings

    def validate(self, *, require_files: bool = True) -> None:
        if (
            self.auth_token in _PLACEHOLDERS
            or not 32 <= len(self.auth_token) <= 256
            or any(
                ord(character) <= 0x20 or ord(character) >= 0x7F
                for character in self.auth_token
            )
        ):
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_AUTH_TOKEN must contain 32-256 visible ASCII characters."
            )
        for label, value in (
            ("environment", self.environment),
            ("namespace", self.namespace),
            ("workload service account", self.workload_service_account),
            ("secret catalog namespace", self.secret_catalog_namespace),
        ):
            if not _DNS_LABEL.fullmatch(value):
                raise ControllerConfigurationError(
                    f"The runtime-controller {label} must be a canonical DNS label."
                )
        if self.image_pull_secret and not _DNS_LABEL.fullmatch(self.image_pull_secret):
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_IMAGE_PULL_SECRET must be a canonical DNS label."
            )
        if not _DNS_LABEL.fullmatch(self.secret_name_prefix):
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_SECRET_NAME_PREFIX must be a canonical DNS label."
            )
        if not _DNS_LABEL.fullmatch(self.secret_catalog_name):
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_SECRET_CATALOG_NAME must be a canonical DNS label."
            )
        try:
            parsed = urlsplit(self.kubernetes_url)
            port = parsed.port
        except ValueError as exc:
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_KUBERNETES_URL is invalid."
            ) from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ControllerConfigurationError(
                "The Kubernetes API URL must be an HTTPS origin without credentials or path."
            )
        if not self.allowed_image_prefixes or any(
            not prefix.endswith("/")
            or "@" in prefix
            or any(character.isspace() for character in prefix)
            for prefix in self.allowed_image_prefixes
        ):
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_ALLOWED_IMAGE_PREFIXES must contain canonical repository prefixes ending in '/'."
            )
        if not 1 <= self.max_replicas <= 100:
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_MAX_REPLICAS must be between 1 and 100."
            )
        if not 1 <= self.request_timeout_seconds <= 60:
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_KUBERNETES_TIMEOUT_SECONDS must be between 1 and 60."
            )
        if (
            not 10 <= self.lease_duration_seconds <= 300
            or self.lease_duration_seconds < 2 * self.request_timeout_seconds
        ):
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_LEASE_DURATION_SECONDS must be between 10 and 300 and at least twice the Kubernetes timeout."
            )
        if not 0.1 <= self.lease_acquire_timeout_seconds <= 30:
            raise ControllerConfigurationError(
                "RUNTIME_CONTROLLER_LEASE_ACQUIRE_TIMEOUT_SECONDS must be between 0.1 and 30."
            )
        if require_files:
            for label, path in (
                ("service-account token", self.kubernetes_token_file),
                ("Kubernetes CA", self.kubernetes_ca_file),
            ):
                if not path.is_absolute() or not path.is_file():
                    raise ControllerConfigurationError(
                        f"The mounted {label} file is missing or is not absolute."
                    )
