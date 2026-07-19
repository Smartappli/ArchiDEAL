"""Stateless OIDC bearer authentication shared by all DEALData layers."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


DEFAULT_OIDC_GROUPS_CLAIM = "groups"
FORBIDDEN_OIDC_GROUPS_CLAIMS = frozenset(
    {
        "scope",
        "scp",
        "roles",
        "realm_access",
        "realm_access.roles",
    },
)
MAX_OIDC_CLAIM_LENGTH = 255
MAX_INTROSPECTION_RESPONSE_BYTES = 1024 * 1024


class _RejectOIDCRedirects(HTTPRedirectHandler):
    """Reject redirects so credentials never leave the configured IdP endpoint."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        del new_url
        raise HTTPError(
            request.full_url,
            code,
            "OIDC introspection redirects are forbidden.",
            headers,
            file_pointer,
        )


def _open_introspection_request(request: Request, *, timeout: float):
    """Open exactly one HTTPS introspection request without following redirects."""

    opener = build_opener(_RejectOIDCRedirects())
    # The caller validates the exact HTTPS endpoint before opening it.
    return opener.open(  # nosec B310
        request,
        timeout=timeout,
    )


@dataclass(frozen=True, slots=True)
class OIDCPrincipal:
    """Request-scoped user-like principal; it is never written to a Django DB."""

    username: str
    oidc_issuer: str
    oidc_subject: str
    oidc_groups: frozenset[str]
    is_staff: bool = False
    is_superuser: bool = False
    is_active: bool = True
    pk: None = None

    @property
    def is_authenticated(self) -> bool:
        """DRF-compatible authenticated-user marker."""

        return True

    @property
    def is_anonymous(self) -> bool:
        """DRF-compatible anonymous-user marker."""

        return False

    def has_perm(self, perm: str, obj: object | None = None) -> bool:
        """Give the configured admin group Django-superuser-equivalent access."""

        del perm, obj
        return self.is_superuser

    def has_perms(self, perm_list: list[str], obj: object | None = None) -> bool:
        """Return whether the principal has every requested permission."""

        return all(self.has_perm(perm, obj=obj) for perm in perm_list)

    def __str__(self) -> str:
        return self.username


@dataclass(frozen=True, slots=True)
class _OIDCConfiguration:
    introspection_url: str
    issuer: str
    audience: str
    client_id: str
    client_secret: str
    groups_claim: str
    read_groups: frozenset[str]
    admin_groups: frozenset[str]
    timeout_seconds: float


class OIDCBearerAuthentication(BaseAuthentication):
    """Introspect an OIDC bearer and build a stateless DEALData principal."""

    keyword = b"bearer"

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization:
            return None
        if authorization[0].lower() != self.keyword:
            return None
        if len(authorization) != 2:
            raise AuthenticationFailed("Invalid bearer token header.")

        try:
            token = authorization[1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid bearer token encoding.") from exc
        if not token or len(token) > 16384 or "\0" in token:
            raise AuthenticationFailed("Invalid bearer token.")

        configuration = self._configuration()
        claims = self._introspect(token, configuration)
        principal = self._principal_from_claims(claims, configuration)
        return principal, None

    def authenticate_header(self, request) -> str | None:
        """Advertise Bearer in configured environments, producing a proper 401."""

        del request
        endpoint = str(
            getattr(settings, "DEALDATA_OIDC_INTROSPECTION_URL", ""),
        ).strip()
        return "Bearer" if endpoint else None

    @classmethod
    def _configuration(cls) -> _OIDCConfiguration:
        string_names = (
            "DEALDATA_OIDC_INTROSPECTION_URL",
            "DEALDATA_OIDC_ISSUER",
            "DEALDATA_OIDC_AUDIENCE",
            "DEALDATA_OIDC_CLIENT_ID",
            "DEALDATA_OIDC_CLIENT_SECRET",
        )
        values: dict[str, str] = {}
        for name in string_names:
            value = getattr(settings, name, "")
            if not isinstance(value, str) or not value or value != value.strip():
                raise AuthenticationFailed("OIDC authentication is not configured.")
            values[name] = value

        introspection_url = values["DEALDATA_OIDC_INTROSPECTION_URL"]
        issuer = values["DEALDATA_OIDC_ISSUER"]
        if not cls._is_canonical_https_url(introspection_url, allow_query=False):
            raise AuthenticationFailed("Invalid OIDC introspection configuration.")
        if not cls._is_canonical_https_url(issuer, allow_query=False):
            raise AuthenticationFailed("Invalid OIDC issuer configuration.")

        groups_claim = getattr(
            settings,
            "DEALDATA_OIDC_GROUPS_CLAIM",
            DEFAULT_OIDC_GROUPS_CLAIM,
        )
        if not cls._is_canonical_claim_name(groups_claim):
            raise AuthenticationFailed("Invalid OIDC groups claim configuration.")

        read_groups = cls._configured_groups("DEALDATA_OIDC_READ_GROUPS")
        admin_groups = cls._configured_groups("DEALDATA_OIDC_ADMIN_GROUPS")
        if not read_groups or not admin_groups or read_groups & admin_groups:
            raise AuthenticationFailed("Invalid OIDC group configuration.")

        timeout = getattr(settings, "DEALDATA_OIDC_TIMEOUT_SECONDS", 3.0)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or float(timeout) <= 0
            or float(timeout) > 30
        ):
            raise AuthenticationFailed("Invalid OIDC timeout configuration.")

        return _OIDCConfiguration(
            introspection_url=introspection_url,
            issuer=issuer,
            audience=values["DEALDATA_OIDC_AUDIENCE"],
            client_id=values["DEALDATA_OIDC_CLIENT_ID"],
            client_secret=values["DEALDATA_OIDC_CLIENT_SECRET"],
            groups_claim=groups_claim,
            read_groups=read_groups,
            admin_groups=admin_groups,
            timeout_seconds=float(timeout),
        )

    @staticmethod
    def _is_canonical_https_url(value: object, *, allow_query: bool) -> bool:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(
                ord(character) < 0x21
                or ord(character) > 0x7E
                or character in {'"', "'", "\\"}
                for character in value
            )
        ):
            return False
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return False
        return bool(
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.fragment == ""
            and (allow_query or parsed.query == "")
            and (port is None or 1 <= port <= 65535)
        )

    @staticmethod
    def _is_canonical_string(value: object) -> bool:
        return bool(
            isinstance(value, str)
            and value
            and value == value.strip()
            and len(value) <= MAX_OIDC_CLAIM_LENGTH
            and "\0" not in value
            and all(
                ord(character) >= 0x20 and ord(character) != 0x7F for character in value
            )
        )

    @classmethod
    def _is_canonical_claim_name(cls, value: object) -> bool:
        return bool(
            cls._is_canonical_string(value)
            and value.casefold() not in FORBIDDEN_OIDC_GROUPS_CLAIMS
        )

    @classmethod
    def _configured_groups(cls, name: str) -> frozenset[str]:
        configured = getattr(settings, name, ())
        if isinstance(configured, str) or not isinstance(
            configured,
            (list, tuple, set, frozenset),
        ):
            return frozenset()
        if any(not cls._is_canonical_string(group) for group in configured):
            return frozenset()
        return frozenset(configured)

    @staticmethod
    def _introspect(
        token: str,
        configuration: _OIDCConfiguration,
    ) -> dict[str, Any]:
        credentials = base64.b64encode(
            f"{configuration.client_id}:{configuration.client_secret}".encode(),
        ).decode("ascii")
        try:
            request = Request(
                configuration.introspection_url,
                data=urlencode({"token": token}).encode("ascii"),
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with _open_introspection_request(
                request,
                timeout=configuration.timeout_seconds,
            ) as response:
                payload = response.read(MAX_INTROSPECTION_RESPONSE_BYTES + 1)
        except (
            HTTPError,
            URLError,
            OSError,
            TimeoutError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise AuthenticationFailed("OIDC token validation failed.") from exc

        if len(payload) > MAX_INTROSPECTION_RESPONSE_BYTES:
            raise AuthenticationFailed("OIDC token validation failed.")
        try:
            claims = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise AuthenticationFailed("OIDC token validation failed.") from exc
        if not isinstance(claims, dict):
            raise AuthenticationFailed("OIDC token validation failed.")
        return claims

    @classmethod
    def _principal_from_claims(
        cls,
        claims: dict[str, Any],
        configuration: _OIDCConfiguration,
    ) -> OIDCPrincipal:
        if claims.get("active") is not True:
            raise AuthenticationFailed("Invalid bearer token.")
        if claims.get("iss") != configuration.issuer:
            raise AuthenticationFailed("Invalid bearer token issuer.")

        audience = claims.get("aud")
        if isinstance(audience, str):
            audiences = {audience}
        elif isinstance(audience, list) and all(
            isinstance(value, str) for value in audience
        ):
            audiences = set(audience)
        else:
            audiences = set()
        if configuration.audience not in audiences:
            raise AuthenticationFailed("Invalid bearer token audience.")

        group_claim = claims.get(configuration.groups_claim)
        if not isinstance(group_claim, list) or any(
            not cls._is_canonical_string(group) for group in group_claim
        ):
            raise AuthenticationFailed(
                "Bearer token has no valid authorization groups."
            )
        groups = frozenset(group_claim)
        is_admin = bool(groups & configuration.admin_groups)
        if not is_admin and not groups & configuration.read_groups:
            raise AuthenticationFailed("Bearer token has no authorized group.")

        subject = claims.get("sub")
        if not cls._is_canonical_string(subject):
            raise AuthenticationFailed("Bearer token has no stable subject.")

        username = next(
            (
                value
                for name in ("preferred_username", "email")
                if cls._is_canonical_string(value := claims.get(name))
            ),
            subject,
        )
        return OIDCPrincipal(
            username=username,
            oidc_issuer=configuration.issuer,
            oidc_subject=subject,
            oidc_groups=groups,
            is_staff=is_admin,
            is_superuser=is_admin,
        )
