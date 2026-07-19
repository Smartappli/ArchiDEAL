import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import (
    ApplicationVersion,
    Dataset,
    HostedApplication,
    Module,
    Tool,
    ToolVersion,
)

User = get_user_model()

SEMVER_PATTERN = r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$"


class ModuleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = [
            "id",
            "name",
            "slug",
            "image",
            "branch",
            "deployment_target",
            "public_path",
            "upstream_host",
            "upstream_port",
            "enabled",
        ]
        read_only_fields = fields


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = [
            "id",
            "name",
            "slug",
            "image",
            "branch",
            "repository_owner",
            "repository_name",
            "source_path",
            "deployment_target",
            "public_path",
            "upstream_host",
            "upstream_port",
            "healthcheck_path",
            "contract_topics",
            "enabled",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ToolVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolVersion
        fields = ["id", "version", "notes", "source", "created_at"]
        read_only_fields = fields


class ApplicationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationVersion
        fields = ["id", "version", "notes", "source", "created_at"]
        read_only_fields = fields


class ToolSerializer(serializers.ModelSerializer):
    modules = ModuleSummarySerializer(many=True, read_only=True)
    module_ids = serializers.PrimaryKeyRelatedField(
        source="modules",
        queryset=Module.objects.all(),
        many=True,
        required=False,
    )
    versions = ToolVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Tool
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "modules",
            "module_ids",
            "current_version",
            "released_at",
            "versions",
            "enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "current_version",
            "released_at",
            "created_at",
            "updated_at",
        ]


class HostedApplicationSerializer(serializers.ModelSerializer):
    modules = ModuleSummarySerializer(many=True, read_only=True)
    module_ids = serializers.PrimaryKeyRelatedField(
        source="modules",
        queryset=Module.objects.all(),
        many=True,
        required=False,
    )
    versions = ApplicationVersionSerializer(many=True, read_only=True)

    class Meta:
        model = HostedApplication
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "modules",
            "module_ids",
            "current_version",
            "released_at",
            "versions",
            "enabled",
            "revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "current_version",
            "released_at",
            "revision",
            "created_at",
            "updated_at",
        ]


class DatasetSerializer(serializers.ModelSerializer):
    """Dataset representation safe for every authorised reader."""

    modules = ModuleSummarySerializer(many=True, read_only=True)
    module_ids = serializers.PrimaryKeyRelatedField(
        source="modules",
        queryset=Module.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "modules",
            "module_ids",
            "enabled",
            "revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "revision", "created_at", "updated_at"]


class DatasetAdminSerializer(DatasetSerializer):
    """Staff representation including the dataset access-control lists."""

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        queryset=User.objects.all(),
        many=True,
        required=False,
    )
    group_ids = serializers.PrimaryKeyRelatedField(
        source="groups",
        queryset=Group.objects.all(),
        many=True,
        required=False,
    )

    class Meta(DatasetSerializer.Meta):
        fields = DatasetSerializer.Meta.fields + ["user_ids", "group_ids"]


class DatasetPrincipalUserSerializer(serializers.ModelSerializer):
    """Minimal, human-readable user reference for dataset ACL editors."""

    label = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    identity_kind = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "label", "email", "is_active", "identity_kind"]
        read_only_fields = fields

    @staticmethod
    def _oidc_identity(user):
        return getattr(user, "oidc_acl_identity", None)

    def get_label(self, user) -> str:
        identity = self._oidc_identity(user)
        if identity is not None:
            return (
                identity.display_name.strip()
                or identity.email.strip()
                or f"OIDC identity {user.pk}"
            )
        return user.get_full_name().strip() or user.email.strip() or user.username

    def get_email(self, user) -> str:
        identity = self._oidc_identity(user)
        if identity is not None and identity.email.strip():
            return identity.email.strip()
        return user.email.strip()

    def get_identity_kind(self, user) -> str:
        return "oidc" if self._oidc_identity(user) is not None else "local"


class DatasetPrincipalGroupSerializer(serializers.ModelSerializer):
    """Minimal group reference for dataset ACL editors."""

    class Meta:
        model = Group
        fields = ["id", "name"]
        read_only_fields = fields


class ModuleAttachSerializer(serializers.Serializer):
    module_id = serializers.PrimaryKeyRelatedField(
        source="module",
        queryset=Module.objects.all(),
    )


class VersionCreateSerializer(serializers.Serializer):
    version = serializers.CharField(max_length=32)
    notes = serializers.CharField(required=False, allow_blank=True)
    source = serializers.CharField(max_length=32, required=False, default="manual")

    def validate_version(self, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(SEMVER_PATTERN, normalized):
            msg = _(
                "Version must follow semantic versioning (example: 1.2.3 or v1.2.3).",
            )
            raise serializers.ValidationError(msg)
        return normalized.lstrip("v")
