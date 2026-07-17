import re

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import ApplicationVersion, HostedApplication, Module, Tool, ToolVersion

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
        read_only_fields = ["id", "created_at", "updated_at"]


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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
