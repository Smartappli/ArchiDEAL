from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.common.oidc import (
    derive_oidc_acl_username,
    validate_approved_oidc_issuer,
    validate_oidc_subject,
)
from apps.hosting.models import Dataset

from .models import OIDCAclIdentity

User = get_user_model()


class OIDCAclIdentityConflict(Exception):
    """The requested stable identity cannot safely claim its local ACL user."""


@dataclass(frozen=True)
class OIDCAclProvisioningResult:
    identity: OIDCAclIdentity
    created: bool
    metadata_updated: bool


@dataclass(frozen=True)
class OIDCAclDeprovisioningResult:
    identity_id: int
    user_id: int
    acl_username: str


def _assert_consistent_binding(
    identity: OIDCAclIdentity,
    expected_username: str,
) -> None:
    user = identity.user
    if user.username != expected_username:
        raise OIDCAclIdentityConflict(
            "The existing OIDC identity is linked to an unexpected ACL username."
        )
    if user.has_usable_password() or user.is_staff or user.is_superuser:
        raise OIDCAclIdentityConflict(
            "The existing OIDC identity is not bound to an unprivileged "
            "passwordless user."
        )


def _refresh_metadata(
    identity: OIDCAclIdentity,
    *,
    display_name: str | None,
    email: str | None,
) -> bool:
    changed_fields: list[str] = []
    for field_name, value in (("display_name", display_name), ("email", email)):
        if value is not None and getattr(identity, field_name) != value:
            setattr(identity, field_name, value)
            changed_fields.append(field_name)
    if changed_fields:
        identity.save(update_fields=[*changed_fields, "updated_at"])
    return bool(changed_fields)


def _provision_once(
    *,
    issuer: str,
    subject: str,
    display_name: str | None,
    email: str | None,
) -> OIDCAclProvisioningResult:
    expected_username = derive_oidc_acl_username(issuer, subject)
    with transaction.atomic():
        identity = (
            OIDCAclIdentity.objects.select_for_update()
            .select_related("user")
            .filter(issuer=issuer, subject=subject)
            .first()
        )
        if identity is not None:
            _assert_consistent_binding(identity, expected_username)
            metadata_updated = _refresh_metadata(
                identity,
                display_name=display_name,
                email=email,
            )
            return OIDCAclProvisioningResult(
                identity=identity,
                created=False,
                metadata_updated=metadata_updated,
            )

        if User.objects.select_for_update().filter(username=expected_username).exists():
            raise OIDCAclIdentityConflict(
                "The derived ACL username is already owned by another Django user."
            )

        user = User(
            username=expected_username,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save(force_insert=True)
        identity = OIDCAclIdentity.objects.create(
            user=user,
            issuer=issuer,
            subject=subject,
            display_name=display_name or "",
            email=email or "",
        )
        return OIDCAclProvisioningResult(
            identity=identity,
            created=True,
            metadata_updated=False,
        )


def provision_oidc_acl_identity(
    *,
    issuer: str,
    subject: str,
    display_name: str | None = None,
    email: str | None = None,
) -> OIDCAclProvisioningResult:
    """Create or idempotently return one stable OIDC ACL identity."""

    issuer = validate_approved_oidc_issuer(
        issuer,
        str(getattr(settings, "DEALHOST_OIDC_ISSUER", "")),
    )
    subject = validate_oidc_subject(subject)
    try:
        return _provision_once(
            issuer=issuer,
            subject=subject,
            display_name=display_name,
            email=email,
        )
    except IntegrityError as exc:
        # A concurrent request can win either uniqueness constraint after our
        # initial lookup. Re-read once after rollback and only accept the exact,
        # internally consistent issuer/subject binding.
        expected_username = derive_oidc_acl_username(issuer, subject)
        with transaction.atomic():
            identity = (
                OIDCAclIdentity.objects.select_for_update()
                .select_related("user")
                .filter(issuer=issuer, subject=subject)
                .first()
            )
            if identity is None:
                if User.objects.filter(username=expected_username).exists():
                    raise OIDCAclIdentityConflict(
                        "The derived ACL username is already owned by another "
                        "Django user."
                    ) from exc
                raise
            _assert_consistent_binding(identity, expected_username)
            metadata_updated = _refresh_metadata(
                identity,
                display_name=display_name,
                email=email,
            )
            return OIDCAclProvisioningResult(
                identity=identity,
                created=False,
                metadata_updated=metadata_updated,
            )


def deprovision_oidc_acl_identity(
    *,
    identity_id: int,
) -> OIDCAclDeprovisioningResult:
    """Delete an unused OIDC ACL identity and its technical user atomically."""

    with transaction.atomic():
        identity = OIDCAclIdentity.objects.select_for_update().get(pk=identity_id)
        user = User.objects.select_for_update().get(pk=identity.user_id)
        identity.user = user
        expected_username = derive_oidc_acl_username(
            identity.issuer,
            identity.subject,
        )
        _assert_consistent_binding(identity, expected_username)

        blockers: list[str] = []
        if Dataset.users.through.objects.filter(user_id=user.pk).exists():
            blockers.append("dataset_acl")
        if User.groups.through.objects.filter(user_id=user.pk).exists():
            blockers.append("groups")
        if User.user_permissions.through.objects.filter(user_id=user.pk).exists():
            blockers.append("user_permissions")
        if blockers:
            raise OIDCAclIdentityConflict(
                "The OIDC ACL identity is still referenced by access-control "
                f"assignments: {', '.join(blockers)}."
            )

        result = OIDCAclDeprovisioningResult(
            identity_id=identity.pk,
            user_id=user.pk,
            acl_username=user.username,
        )
        identity.delete()
        user.delete()
        return result
