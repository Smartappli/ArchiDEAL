from __future__ import annotations

import hmac
from dataclasses import dataclass

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
    """Authenticate API service accounts from settings-backed bearer tokens."""

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

        raise AuthenticationFailed("Invalid bearer token.")

    def authenticate_header(self, request) -> str:
        return "Bearer"

    @staticmethod
    def _matches(token: str, candidates: tuple[str, ...]) -> bool:
        return any(
            candidate and hmac.compare_digest(token, candidate)
            for candidate in candidates
        )
