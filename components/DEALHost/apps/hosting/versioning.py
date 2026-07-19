from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone


class VersionMetadataConflict(ValueError):
    """A published version number was reused with different metadata."""


class VersionRevisionConflict(ValueError):
    """The parent catalog resource changed before a version was published."""

    def __init__(self, resource) -> None:
        super().__init__(resource.revision)
        self.resource = resource


@dataclass(frozen=True)
class VersionPublication:
    resource: Any
    version: Any
    created: bool


def publish_immutable_version(
    resource,
    validated_data: dict,
    *,
    expected_revision: int | None = None,
) -> VersionPublication:
    """Publish immutable version metadata and advance the catalog atomically.

    An exact replay returns the existing row without changing either the version
    or the parent catalog pointer. A version number can therefore never be used
    to replace release notes or their source.
    """

    version = validated_data["version"]
    notes = validated_data.get("notes", "")
    source = validated_data.get("source", "manual")

    with transaction.atomic():
        locked_resource = type(resource).objects.select_for_update().get(pk=resource.pk)
        if (
            expected_revision is not None
            and locked_resource.revision != expected_revision
        ):
            raise VersionRevisionConflict(locked_resource)
        version_obj, created = locked_resource.versions.get_or_create(
            version=version,
            defaults={"notes": notes, "source": source},
        )
        if not created:
            if version_obj.notes != notes or version_obj.source != source:
                raise VersionMetadataConflict(version)
            return VersionPublication(locked_resource, version_obj, False)

        locked_resource.current_version = version
        locked_resource.released_at = timezone.now()
        update_fields = ["current_version", "released_at", "updated_at"]
        if hasattr(locked_resource, "revision"):
            locked_resource.revision += 1
            update_fields.append("revision")
        locked_resource.save(
            update_fields=update_fields,
        )

    return VersionPublication(locked_resource, version_obj, True)
