from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class SettingsTokenUser:
    username: str
    is_staff: bool = False
    is_superuser: bool = False
    is_active: bool = True

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
    def _claim_values(claims: dict[str, Any]) -> set[str]:
        values: set[str] = set()
        for claim_name in ("groups", "roles"):
            claim = claims.get(claim_name)
            if isinstance(claim, list):
                values.update(str(value) for value in claim)
        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict) and isinstance(
            realm_access.get("roles"),
            list,
        ):
            values.update(str(value) for value in realm_access["roles"])
        scope = claims.get("scope")
        if isinstance(scope, str):
            values.update(scope.split())
        return values

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

        identities = cls._claim_values(claims)
        admin_groups = set(settings.DEALHOST_OIDC_ADMIN_GROUPS)
        read_groups = set(settings.DEALHOST_OIDC_READ_GROUPS)
        is_admin = bool(identities & admin_groups)
        if not is_admin and not identities & read_groups:
            raise AuthenticationFailed("Bearer token has no authorized group.")

        username = next(
            (
                str(claims[name])
                for name in ("preferred_username", "email", "sub")
                if claims.get(name)
            ),
            "oidc-operator",
        )
        return SettingsTokenUser(
            username=username,
            is_staff=is_admin,
            is_superuser=is_admin,
        )
