import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import (
    ApplicationVersion,
    Dataset,
    HostedApplication,
    Module,
    ModuleRuntimeProfile,
    RuntimeComponent,
    RuntimeDeployment,
    RuntimeEnvironment,
    RuntimeOperation,
    Tool,
    ToolVersion,
)

User = get_user_model()

SEMVER_PATTERN = r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$"
RUNTIME_CONFIG_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
RUNTIME_SECRET_KEY_PATTERN = re.compile(
    r"(?:PASSWORD|PASSWD|TOKEN|SECRET|PRIVATE|CREDENTIAL|API_KEY|ACCESS_KEY)",
    re.IGNORECASE,
)
RUNTIME_SECRET_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


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


def _runtime_profile_rules(application: HostedApplication) -> dict[str, dict[str, set[str]]]:
    rules: dict[str, dict[str, set[str]]] = {}
    for module in application.modules.all():
        try:
            profile = module.runtime_profile
        except ModuleRuntimeProfile.DoesNotExist:
            rules[module.slug] = {"plain": set(), "secret": set()}
            continue
        if not profile.enabled or profile.verified_at is None:
            rules[module.slug] = {"plain": set(), "secret": set()}
            continue
        configuration = profile.spec.get("configuration", {})
        if not isinstance(configuration, dict):
            raise serializers.ValidationError(
                f"Runtime profile for {module.slug} has an invalid configuration contract."
            )
        plain = configuration.get("plain", [])
        secret = configuration.get("secret", [])
        if (
            not isinstance(plain, list)
            or not isinstance(secret, list)
            or any(not isinstance(key, str) for key in [*plain, *secret])
        ):
            raise serializers.ValidationError(
                f"Runtime profile for {module.slug} has invalid configuration keys."
            )
        rules[module.slug] = {"plain": set(plain), "secret": set(secret)}
    return rules


def _validate_component_values(
    value: object,
    *,
    application: HostedApplication,
    secret: bool,
) -> dict[str, dict[str, str]]:
    label = "Secret references" if secret else "Configuration"
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{label} must be keyed by module slug.")
    rules = _runtime_profile_rules(application)
    unknown_modules = sorted(set(value) - set(rules))
    if unknown_modules:
        raise serializers.ValidationError(
            f"{label} contains modules outside the application: "
            + ", ".join(unknown_modules)
        )
    normalized: dict[str, dict[str, str]] = {}
    total_size = 0
    for module_slug, raw_values in value.items():
        if not isinstance(raw_values, dict) or len(raw_values) > 50:
            raise serializers.ValidationError(
                f"{label} for {module_slug} must be an object with at most 50 entries."
            )
        allowed = rules[module_slug]["secret" if secret else "plain"]
        component: dict[str, str] = {}
        for raw_key, raw_value in raw_values.items():
            if (
                not isinstance(raw_key, str)
                or not RUNTIME_CONFIG_KEY_PATTERN.fullmatch(raw_key)
                or raw_key not in allowed
            ):
                raise serializers.ValidationError(
                    f"{raw_key} is not allowed by the runtime profile for {module_slug}."
                )
            if not isinstance(raw_value, str):
                raise serializers.ValidationError(f"{raw_key} must contain a string.")
            if secret:
                if not RUNTIME_SECRET_REFERENCE_PATTERN.fullmatch(raw_value):
                    raise serializers.ValidationError(
                        f"{raw_key} must reference one canonical logical secret name."
                    )
            elif RUNTIME_SECRET_KEY_PATTERN.search(raw_key):
                raise serializers.ValidationError(
                    f"{raw_key} looks sensitive and must use secret_refs."
                )
            if len(raw_value) > 2048:
                raise serializers.ValidationError(f"{raw_key} is too long.")
            total_size += len(raw_key) + len(raw_value)
            if total_size > 16_384:
                raise serializers.ValidationError(f"{label} is limited to 16 KiB.")
            component[raw_key] = raw_value
        normalized[module_slug] = component
    return normalized


def validate_runtime_configuration(
    value: object,
    *,
    application: HostedApplication,
) -> dict[str, dict[str, str]]:
    return _validate_component_values(value, application=application, secret=False)


def validate_runtime_secret_references(
    value: object,
    *,
    application: HostedApplication,
) -> dict[str, dict[str, str]]:
    return _validate_component_values(value, application=application, secret=True)


def validate_runtime_scaling(
    value: object,
    *,
    application: HostedApplication,
) -> dict[str, dict[str, int | str]]:
    if not isinstance(value, dict):
        raise serializers.ValidationError("Scaling must be a JSON object keyed by module slug.")
    module_slugs = {module.slug for module in application.modules.all()}
    unknown_slugs = sorted(set(value) - module_slugs)
    if unknown_slugs:
        raise serializers.ValidationError(
            "Scaling contains modules outside the application: " + ", ".join(unknown_slugs)
        )
    normalized: dict[str, dict[str, int | str]] = {}
    for module_slug in sorted(module_slugs):
        raw_policy = value.get(module_slug, {"mode": "fixed", "replicas": 1})
        if not isinstance(raw_policy, dict):
            raise serializers.ValidationError(f"Scaling for {module_slug} must be an object.")
        mode = raw_policy.get("mode")
        if mode == "fixed":
            if set(raw_policy) - {"mode", "replicas"}:
                raise serializers.ValidationError(
                    f"Scaling for {module_slug} contains unsupported fixed-mode fields."
                )
            replicas = raw_policy.get("replicas")
            if not isinstance(replicas, int) or isinstance(replicas, bool) or not 1 <= replicas <= 50:
                raise serializers.ValidationError(
                    f"Fixed replicas for {module_slug} must be between 1 and 50."
                )
            normalized[module_slug] = {"mode": "fixed", "replicas": replicas}
            continue
        if mode == "autoscale":
            allowed = {
                "mode",
                "min_replicas",
                "max_replicas",
                "target_cpu_utilization",
            }
            if set(raw_policy) - allowed:
                raise serializers.ValidationError(
                    f"Scaling for {module_slug} contains unsupported autoscale fields."
                )
            minimum = raw_policy.get("min_replicas")
            maximum = raw_policy.get("max_replicas")
            target = raw_policy.get("target_cpu_utilization", 70)
            values = (minimum, maximum, target)
            if any(not isinstance(item, int) or isinstance(item, bool) for item in values):
                raise serializers.ValidationError(
                    f"Autoscaling values for {module_slug} must be integers."
                )
            assert isinstance(minimum, int) and isinstance(maximum, int) and isinstance(target, int)
            if not 1 <= minimum <= maximum <= 50 or not 10 <= target <= 90:
                raise serializers.ValidationError(
                    f"Autoscaling for {module_slug} must use 1-50 replicas and a 10-90 CPU target."
                )
            normalized[module_slug] = {
                "mode": "autoscale",
                "min_replicas": minimum,
                "max_replicas": maximum,
                "target_cpu_utilization": target,
            }
            continue
        raise serializers.ValidationError(
            f"Scaling mode for {module_slug} must be fixed or autoscale."
        )
    return normalized


class RuntimeEnvironmentSerializer(serializers.ModelSerializer):
    enabled = serializers.SerializerMethodField()

    class Meta:
        model = RuntimeEnvironment
        fields = [
            "slug",
            "name",
            "description",
            "orchestrator",
            "enabled",
            "capabilities",
            "policy",
        ]
        read_only_fields = fields

    def get_enabled(self, environment: RuntimeEnvironment) -> bool:
        return bool(environment.enabled and settings.RUNTIME_ENABLED)


class RuntimeComponentSerializer(serializers.ModelSerializer):
    module_id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(source="module.slug", read_only=True)
    last_error = serializers.SerializerMethodField()

    class Meta:
        model = RuntimeComponent
        fields = [
            "module_id",
            "slug",
            "image_digest",
            "desired_replicas",
            "ready_replicas",
            "available_replicas",
            "state",
            "health",
            "restart_count",
            "last_error",
        ]
        read_only_fields = fields

    def get_last_error(self, component: RuntimeComponent) -> str | None:
        return component.last_error or None


class RuntimeOperationSerializer(serializers.ModelSerializer):
    deployment_id = serializers.UUIDField(read_only=True)
    type = serializers.CharField(source="operation_type", read_only=True)
    result = serializers.SerializerMethodField()

    class Meta:
        model = RuntimeOperation
        fields = [
            "id",
            "deployment_id",
            "type",
            "status",
            "requested_at",
            "started_at",
            "finished_at",
            "progress",
            "result",
            "error",
        ]
        read_only_fields = fields

    def get_result(self, operation: RuntimeOperation) -> object:
        if operation.operation_type == RuntimeOperation.OperationType.LOG_SNAPSHOT:
            return cache.get(f"dealhost:runtime-log:{operation.id}")
        return operation.result


class RuntimeDeploymentSerializer(serializers.ModelSerializer):
    application = serializers.SerializerMethodField()
    environment = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    version = serializers.CharField(read_only=True)
    components = RuntimeComponentSerializer(many=True, read_only=True)
    last_error = serializers.SerializerMethodField()

    class Meta:
        model = RuntimeDeployment
        fields = [
            "id",
            "application",
            "environment",
            "version",
            "desired_state",
            "observed_state",
            "scaling",
            "configuration",
            "secret_refs",
            "components",
            "last_error",
            "last_reconciled_at",
            "revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_application(self, deployment: RuntimeDeployment) -> dict[str, object]:
        return {
            "id": deployment.application_id,
            "name": deployment.application.name,
            "slug": deployment.application.slug,
        }

    def get_last_error(self, deployment: RuntimeDeployment) -> str | None:
        return deployment.last_error or None


class RuntimeDeploymentCreateSerializer(serializers.Serializer):
    application_id = serializers.PrimaryKeyRelatedField(
        queryset=HostedApplication.objects.prefetch_related("modules", "versions"),
        source="application",
    )
    environment = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=RuntimeEnvironment.objects.filter(enabled=True),
    )
    version = serializers.RegexField(
        SEMVER_PATTERN,
        max_length=32,
        required=False,
        allow_blank=True,
    )
    scaling = serializers.JSONField(default=dict)
    configuration = serializers.JSONField(default=dict)
    secret_refs = serializers.JSONField(default=dict)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        application = attrs["application"]
        assert isinstance(application, HostedApplication)
        if not application.enabled:
            raise serializers.ValidationError(
                {"application_id": "Disabled applications cannot be deployed."}
            )
        modules = list(application.modules.all())
        if not modules:
            raise serializers.ValidationError(
                {"application_id": "The application has no deployable modules."}
            )
        if any(not module.enabled for module in modules):
            raise serializers.ValidationError(
                {"application_id": "Every application module must be enabled."}
            )
        if any(not module.image.strip() for module in modules):
            raise serializers.ValidationError(
                {"application_id": "Every application module must declare an image."}
            )
        version = str(attrs.get("version") or application.current_version).strip()
        if not re.fullmatch(SEMVER_PATTERN, version):
            raise serializers.ValidationError({"version": "A semantic version is required."})
        if not application.versions.filter(version=version).exists():
            raise serializers.ValidationError(
                {"version": "Only published application versions can be deployed."}
            )
        attrs["version"] = version
        attrs["scaling"] = validate_runtime_scaling(
            attrs["scaling"],
            application=application,
        )
        attrs["configuration"] = validate_runtime_configuration(
            attrs["configuration"], application=application
        )
        attrs["secret_refs"] = validate_runtime_secret_references(
            attrs["secret_refs"], application=application
        )
        return attrs


class RuntimeDeploymentUpdateSerializer(serializers.Serializer):
    scaling = serializers.JSONField(required=False)
    configuration = serializers.JSONField(required=False)
    secret_refs = serializers.JSONField(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not attrs:
            raise serializers.ValidationError("At least one runtime field is required.")
        return attrs

    def validate_configuration(self, value: object) -> dict[str, dict[str, str]]:
        deployment = self.context["deployment"]
        return validate_runtime_configuration(value, application=deployment.application)

    def validate_scaling(self, value: object) -> dict[str, dict[str, int | str]]:
        deployment = self.context["deployment"]
        return validate_runtime_scaling(value, application=deployment.application)

    def validate_secret_refs(self, value: object) -> dict[str, dict[str, str]]:
        deployment = self.context["deployment"]
        return validate_runtime_secret_references(value, application=deployment.application)


class RuntimeActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["start", "stop", "restart", "scale"]
    )
    component = serializers.SlugField(required=False)
    replicas = serializers.IntegerField(min_value=1, max_value=50, required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["action"] == "scale":
            if "component" not in attrs or "replicas" not in attrs:
                raise serializers.ValidationError(
                    "Scale requires a component and replicas."
                )
        elif "component" in attrs or "replicas" in attrs:
            raise serializers.ValidationError(
                "Component and replicas are accepted only for scale."
            )
        return attrs


class RuntimeLogRequestSerializer(serializers.Serializer):
    component = serializers.SlugField()
    tail_lines = serializers.IntegerField(min_value=1, max_value=1000)
    since_seconds = serializers.IntegerField(min_value=1, max_value=604800)


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
