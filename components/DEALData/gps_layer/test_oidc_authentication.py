"""Security tests for DEALData's shared stateless OIDC boundary."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from urllib.request import Request
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import override_settings
import pytest
from rest_framework.test import APIClient, APIRequestFactory

from dealdata_common.authentication import (
    OIDCBearerAuthentication,
    _RejectOIDCRedirects,
)


OIDC_SETTINGS = {
    "DEALDATA_OIDC_INTROSPECTION_URL": (
        "https://identity.example.test/oauth2/introspect"
    ),
    "DEALDATA_OIDC_ISSUER": "https://identity.example.test/realms/archideal",
    "DEALDATA_OIDC_AUDIENCE": "archideal-production",
    "DEALDATA_OIDC_CLIENT_ID": "dealdata",
    "DEALDATA_OIDC_CLIENT_SECRET": "test-client-secret",  # nosec B105
    "DEALDATA_OIDC_GROUPS_CLAIM": "groups",
    "DEALDATA_OIDC_READ_GROUPS": ("archideal-readers",),
    "DEALDATA_OIDC_ADMIN_GROUPS": ("archideal-admins",),
    "DEALDATA_OIDC_TIMEOUT_SECONDS": 2.0,
}


class FakeIntrospectionResponse:
    """Small context-managed HTTP response used by the urllib boundary."""

    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def read(self, size: int = -1) -> bytes:
        return self.payload[:size] if size >= 0 else self.payload


def oidc_claims(*, groups: list[str] | None = None) -> dict[str, object]:
    """Return a valid, sanitized introspection payload."""

    claims: dict[str, object] = {
        "active": True,
        "iss": OIDC_SETTINGS["DEALDATA_OIDC_ISSUER"],
        "aud": [OIDC_SETTINGS["DEALDATA_OIDC_AUDIENCE"]],
        "sub": "operator-123",
        "preferred_username": "operator",
    }
    if groups is not None:
        claims["groups"] = groups
    return claims


def configure_introspection(mocked_open: Mock, claims: object) -> None:
    mocked_open.return_value = FakeIntrospectionResponse(claims)


def test_oidc_authentication_precedes_session_and_basic() -> None:
    """Bearer authentication wins without removing local maintenance auth."""

    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "dealdata_common.authentication.OIDCBearerAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ]


@pytest.mark.django_db
@override_settings(**OIDC_SETTINGS)
@patch("dealdata_common.authentication._open_introspection_request")
def test_oidc_admin_can_list_gps_and_uses_confidential_introspection(
    mocked_open: Mock,
) -> None:
    """An admin bearer is introspected server-side before sensitive reads."""

    configure_introspection(mocked_open, oidc_claims(groups=["archideal-admins"]))

    response = APIClient().get(
        "/api/wildfi/gps/",
        HTTP_AUTHORIZATION="Bearer edge-access-token",
    )

    assert response.status_code == 200
    request = mocked_open.call_args.args[0]
    assert request.full_url == OIDC_SETTINGS["DEALDATA_OIDC_INTROSPECTION_URL"]
    assert parse_qs(request.data.decode("ascii")) == {
        "token": ["edge-access-token"],
    }
    scheme, encoded_credentials = request.get_header("Authorization").split()
    assert scheme == "Basic"
    assert base64.b64decode(encoded_credentials).decode() == (
        "dealdata:test-client-secret"
    )
    assert mocked_open.call_args.kwargs["timeout"] == 2.0


@pytest.mark.django_db
@override_settings(**OIDC_SETTINGS)
@patch("dealdata_common.authentication._open_introspection_request")
def test_oidc_admin_becomes_a_stateless_staff_principal(
    mocked_open: Mock,
) -> None:
    """The admin group maps to staff without creating a Django user row."""

    configure_introspection(mocked_open, oidc_claims(groups=["archideal-admins"]))
    request = APIRequestFactory().get(
        "/api/gps-sensors/",
        HTTP_AUTHORIZATION="Bearer admin-access-token",
    )

    principal, authentication = OIDCBearerAuthentication().authenticate(request)

    assert authentication is None
    assert principal.is_authenticated
    assert principal.is_staff
    assert principal.is_superuser
    assert principal.pk is None
    assert principal.oidc_subject == "operator-123"
    assert principal.oidc_groups == frozenset({"archideal-admins"})


@pytest.mark.django_db
@override_settings(**OIDC_SETTINGS)
@patch("dealdata_common.authentication._open_introspection_request")
def test_oidc_reader_cannot_use_admin_metadata_api(mocked_open: Mock) -> None:
    """Scope and generic role claims cannot elevate a configured read group."""

    claims = oidc_claims(groups=["archideal-readers"])
    claims.update(
        {
            "scope": "openid archideal-admins",
            "roles": ["archideal-admins"],
            "realm_access": {"roles": ["archideal-admins"]},
        },
    )
    configure_introspection(mocked_open, claims)

    response = APIClient().get(
        "/api/gps-sensors/",
        HTTP_AUTHORIZATION="Bearer reader-access-token",
    )

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(**{**OIDC_SETTINGS, "DEALDATA_OIDC_GROUPS_CLAIM": "entitlements"})
@patch("dealdata_common.authentication._open_introspection_request")
def test_oidc_uses_only_the_dedicated_configured_groups_claim(
    mocked_open: Mock,
) -> None:
    """An admin name in another claim does not affect authorization."""

    claims = oidc_claims(groups=["archideal-admins"])
    claims["entitlements"] = ["archideal-readers"]
    configure_introspection(mocked_open, claims)

    response = APIClient().get(
        "/api/gps-sensors/",
        HTTP_AUTHORIZATION="Bearer reader-access-token",
    )

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "claims",
    [
        {**oidc_claims(groups=["archideal-readers"]), "active": False},
        {
            **oidc_claims(groups=["archideal-readers"]),
            "iss": "https://other-issuer.example.test",
        },
        {
            **oidc_claims(groups=["archideal-readers"]),
            "aud": ["different-audience"],
        },
        oidc_claims(groups=["unapproved-group"]),
        {
            **oidc_claims(groups=None),
            "roles": ["archideal-admins"],
        },
        oidc_claims(groups=["archideal-admins", "malformed\ngroup"]),
        {**oidc_claims(groups=["archideal-readers"]), "sub": " bad-subject"},
    ],
    ids=(
        "inactive",
        "wrong-issuer",
        "wrong-audience",
        "wrong-group",
        "generic-role-only",
        "malformed-group",
        "noncanonical-subject",
    ),
)
@override_settings(**OIDC_SETTINGS)
@patch("dealdata_common.authentication._open_introspection_request")
def test_oidc_invalid_security_claims_fail_closed(
    mocked_open: Mock,
    claims: dict[str, object],
) -> None:
    """Every identity and authorization condition is mandatory."""

    configure_introspection(mocked_open, claims)

    response = APIClient().get(
        "/api/wildfi/gps/",
        HTTP_AUTHORIZATION="Bearer rejected-access-token",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(**OIDC_SETTINGS)
@patch(
    "dealdata_common.authentication._open_introspection_request",
    side_effect=URLError("identity provider unavailable"),
)
def test_oidc_introspection_outage_fails_closed(mocked_open: Mock) -> None:
    """An IdP outage never falls through to another authentication backend."""

    response = APIClient().get(
        "/api/wildfi/gps/",
        HTTP_AUTHORIZATION="Bearer unavailable-access-token",
    )

    assert response.status_code == 401
    mocked_open.assert_called_once()


@pytest.mark.django_db
@override_settings(
    **{**OIDC_SETTINGS, "DEALDATA_OIDC_GROUPS_CLAIM": "roles"},
)
@patch("dealdata_common.authentication._open_introspection_request")
def test_reserved_groups_claim_configuration_fails_before_network(
    mocked_open: Mock,
) -> None:
    """Ambiguous scope/role claims cannot be selected as the group authority."""

    response = APIClient().get(
        "/api/wildfi/gps/",
        HTTP_AUTHORIZATION="Bearer rejected-access-token",
    )

    assert response.status_code == 401
    mocked_open.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid_setting",
    [
        {"DEALDATA_OIDC_INTROSPECTION_URL": "http://identity.example.test/introspect"},
        {
            "DEALDATA_OIDC_INTROSPECTION_URL": (
                "https://identity.example.test/introspect?relay=forbidden"
            )
        },
        {"DEALDATA_OIDC_CLIENT_SECRET": ""},
        {"DEALDATA_OIDC_ADMIN_GROUPS": ("archideal-readers",)},
        {"DEALDATA_OIDC_TIMEOUT_SECONDS": 0},
    ],
    ids=(
        "plaintext-endpoint",
        "endpoint-query",
        "missing-client-secret",
        "overlapping-groups",
        "zero-timeout",
    ),
)
@patch("dealdata_common.authentication._open_introspection_request")
def test_invalid_oidc_configuration_fails_before_network(
    mocked_open: Mock,
    invalid_setting: dict[str, object],
) -> None:
    """Partial, ambiguous, or unsafe configuration cannot authenticate."""

    with override_settings(**{**OIDC_SETTINGS, **invalid_setting}):
        response = APIClient().get(
            "/api/wildfi/gps/",
            HTTP_AUTHORIZATION="Bearer rejected-access-token",
        )

    assert response.status_code == 401
    mocked_open.assert_not_called()


@pytest.mark.django_db
@override_settings(**OIDC_SETTINGS, DEALDATA_INGEST_TOKEN="ingest-test-token")
@patch("dealdata_common.authentication._open_introspection_request")
def test_existing_ingestion_token_boundary_ignores_oidc_authentication(
    mocked_open: Mock,
) -> None:
    """The DEALIoT ingestion path keeps its dedicated shared-token contract."""

    response = APIClient().post(
        "/api/ingest/wildfi/gps/",
        {
            "event_id": "gps-oidc-ingest-test",
            "device_id": "wildfi-test",
            "timestamp": "2026-07-19T12:00:00Z",
            "latitude": 50.6,
            "longitude": 5.5,
        },
        format="json",
        HTTP_AUTHORIZATION="Bearer deliberately-not-introspected",
        HTTP_X_DEALDATA_INGEST_TOKEN="ingest-test-token",
    )

    assert response.status_code == 201
    mocked_open.assert_not_called()


def test_oidc_redirect_handler_rejects_cross_endpoint_relay() -> None:
    """Redirects cannot relay the bearer or Basic credentials to another URL."""

    request = Request(
        OIDC_SETTINGS["DEALDATA_OIDC_INTROSPECTION_URL"],
        headers={"Authorization": "Basic test-credentials"},
        method="POST",
    )

    with pytest.raises(HTTPError, match="redirects are forbidden"):
        _RejectOIDCRedirects().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://attacker.example.test/collect",
        )
