from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .oidc import derive_oidc_acl_username


DEFAULT_OIDC_GROUPS_CLAIM = "groups"
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
class SettingsTokenUser:
    username: str
    is_staff: bool = False
    is_superuser: bool = False
    is_active: bool = True
    oidc_issuer: str | None = None
    oidc_subject: str | None = None
    oidc_groups: frozenset[str] = frozenset()

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def has_perm(self, perm: str, obj: object | None = None) -> bool:
        return self.is_superuser

    def has_perms(self, perm_list: list[str], obj: object | None = None) -> bool:
        return all(self.has_perm(perm, obj=obj) for perm in perm_list)

    @property
    def acl_username(self) -> str:
        """Stable local ACL key for a token-backed identity."""

        if self.oidc_issuer and self.oidc_subject:
            return derive_oidc_acl_username(self.oidc_issuer, self.oidc_subject)
        return self.username


class EnvBearerAuthentication(BaseAuthentication):
    """Authenticate static service tokens or an edge-validated OIDC bearer token."""

    keyword = "bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None
        if auth[0].lower() != self.keyword.encode():
            return None
        if len(auth) != 2:
            raise AuthenticationFailed("Invalid bearer token header.")

        try:
            token = auth[1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid bearer token encoding.") from exc

        admin_tokens = tuple(getattr(settings, "DEALHOST_ADMIN_API_TOKENS", ()))
        if self._matches(token, admin_tokens):
            return (
                SettingsTokenUser(
                    username="dealhost-admin-token",
                    is_staff=True,
                    is_superuser=True,
                ),
                token,
            )

        api_tokens = tuple(getattr(settings, "DEALHOST_API_TOKENS", ()))
        if self._matches(token, api_tokens):
            return (SettingsTokenUser(username="dealhost-api-token"), token)

        oidc_user = self._authenticate_oidc(token)
        if oidc_user is not None:
            return (oidc_user, token)

        raise AuthenticationFailed("Invalid bearer token.")

    def authenticate_header(self, request) -> str:
        return "Bearer"

    @staticmethod
    def _matches(token: str, candidates: tuple[str, ...]) -> bool:
        return any(
            candidate and hmac.compare_digest(token, candidate)
            for candidate in candidates
        )

    @staticmethod
    def _configured_groups_claim_name() -> str | None:
        configured = getattr(settings, "DEALHOST_OIDC_GROUPS_CLAIM", None)
        if configured is None:
            configured = os.getenv(
                "DEALHOST_OIDC_GROUPS_CLAIM",
                DEFAULT_OIDC_GROUPS_CLAIM,
            )
        if not isinstance(configured, str):
            return None
        claim_name = configured.strip()
        if (
            not claim_name
            or configured != claim_name
            or len(claim_name) > 255
            or "\0" in claim_name
            or claim_name.casefold() in FORBIDDEN_OIDC_GROUPS_CLAIMS
        ):
            return None
        return claim_name

    @classmethod
    def _claim_values(cls, claims: dict[str, Any]) -> set[str]:
        """Read authorization groups from exactly one configured top-level claim."""

        claim_name = cls._configured_groups_claim_name()
        if claim_name is None:
            raise AuthenticationFailed("Invalid OIDC groups claim configuration.")
        claim = claims.get(claim_name)
        if not isinstance(claim, list):
            return set()
        if any(
            not isinstance(value, str) or not value.strip() or value != value.strip()
            for value in claim
        ):
            return set()
        return set(claim)

    @classmethod
    def _authenticate_oidc(cls, token: str) -> SettingsTokenUser | None:
        endpoint = str(getattr(settings, "DEALHOST_OIDC_INTROSPECTION_URL", "")).strip()
        if not endpoint:
            return None

        try:
            response = httpx.post(
                endpoint,
                data={"token": token},
                auth=(
                    settings.DEALHOST_OIDC_CLIENT_ID,
                    settings.DEALHOST_OIDC_CLIENT_SECRET,
                ),
                headers={"Accept": "application/json"},
                timeout=settings.DEALHOST_OIDC_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            claims = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise AuthenticationFailed("OIDC token validation failed.") from exc

        if not isinstance(claims, dict) or claims.get("active") is not True:
            raise AuthenticationFailed("Invalid bearer token.")
        if claims.get("iss") != settings.DEALHOST_OIDC_ISSUER:
            raise AuthenticationFailed("Invalid bearer token issuer.")

        audience = claims.get("aud")
        if isinstance(audience, str):
            audiences = {audience}
        elif isinstance(audience, list):
            audiences = {str(value) for value in audience}
        else:
            audiences = set()
        if settings.DEALHOST_OIDC_AUDIENCE not in audiences:
            raise AuthenticationFailed("Invalid bearer token audience.")

        authorization_groups = cls._claim_values(claims)
        admin_groups = set(settings.DEALHOST_OIDC_ADMIN_GROUPS)
        read_groups = set(settings.DEALHOST_OIDC_READ_GROUPS)
        is_admin = bool(authorization_groups & admin_groups)
        if not is_admin and not authorization_groups & read_groups:
            raise AuthenticationFailed("Bearer token has no authorized group.")

        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not subject
            or subject != subject.strip()
            or len(subject) > 255
            or "\0" in subject
        ):
            raise AuthenticationFailed("Bearer token has no stable subject.")

        username = next(
            (
                str(claims[name])
                for name in ("preferred_username", "email")
                if claims.get(name)
            ),
            subject,
        )
        return SettingsTokenUser(
            username=username,
            is_staff=is_admin,
            is_superuser=is_admin,
            oidc_issuer=str(claims["iss"]),
            oidc_subject=subject,
            oidc_groups=frozenset(authorization_groups),
        )
