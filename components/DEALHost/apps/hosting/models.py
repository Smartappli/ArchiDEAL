import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Module(models.Model):
    """Un module déployable indépendamment (billing, auth, cms...)."""

    class DeploymentTarget(models.TextChoices):
        COMPOSE = "compose", _("Docker Compose")
        SWARM = "swarm", _("Docker Swarm")
        KUBERNETES = "kubernetes", _("Kubernetes")
        EXTERNAL = "external", _("External service")

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    image = models.CharField(max_length=255)
    branch = models.CharField(max_length=120, default="main")
    repository_owner = models.CharField(max_length=120, blank=True, default="")
    repository_name = models.CharField(max_length=120, blank=True, default="")
    source_path = models.CharField(max_length=255, blank=True, default="")
    deployment_target = models.CharField(
        max_length=32,
        choices=DeploymentTarget.choices,
        default=DeploymentTarget.COMPOSE,
    )
    public_path = models.CharField(max_length=120, blank=True, default="")
    upstream_host = models.CharField(max_length=255, blank=True, default="")
    upstream_port = models.PositiveIntegerField(null=True, blank=True)
    healthcheck_path = models.CharField(max_length=255, blank=True, default="")
    contract_topics = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Module")
        verbose_name_plural = _("Modules")

    def __str__(self) -> str:
        return f"{self.name} ({self.branch})"


class Tool(models.Model):
    """Un outil technique consommant un ou plusieurs modules."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    modules = models.ManyToManyField(Module, related_name="tools", blank=True)
    current_version = models.CharField(max_length=32, default="0.1.0")
    released_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Tool")
        verbose_name_plural = _("Tools")

    def __str__(self) -> str:
        return self.name


class ToolVersion(models.Model):
    """Historique des versions publiées d'un outil."""

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField(max_length=32)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=32, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Tool version")
        verbose_name_plural = _("Tool versions")
        unique_together = ("tool", "version")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.tool.slug}@{self.version}"


class HostedApplication(models.Model):
    """Une application métier pouvant composer un ou plusieurs modules."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    modules = models.ManyToManyField(Module, related_name="applications", blank=True)
    current_version = models.CharField(max_length=32, default="0.1.0")
    released_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Application")
        verbose_name_plural = _("Applications")

    def __str__(self) -> str:
        return self.name


class ApplicationVersion(models.Model):
    """Historique des versions publiées d'une application hébergée."""

    application = models.ForeignKey(
        HostedApplication,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.CharField(max_length=32)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=32, default="manual")
    runtime_snapshot = models.JSONField(default=dict, blank=True)
    runtime_snapshot_digest = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Application version")
        verbose_name_plural = _("Application versions")
        unique_together = ("application", "version")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.application.slug}@{self.version}"


def default_runtime_capabilities() -> dict[str, object]:
    return {
        "start_stop": True,
        "restart": True,
        "scaling": {
            "fixed": {"min_replicas": 1, "max_replicas": 10},
            "autoscaling": {"enabled": False, "min_replicas": 1, "max_replicas": 10},
        },
        "logs": {"max_lines": 1000, "max_bytes": 262144},
        "domains": False,
    }


def default_runtime_policy() -> dict[str, object]:
    return {
        "requires_image_digest": True,
        "allowed_registries": ["ghcr.io/smartappli/"],
        "stateless_only": True,
    }


def default_operation_progress() -> dict[str, object]:
    return {"stage": "queued", "percent": None}


class RuntimeEnvironment(models.Model):
    """Operator allowlist for an isolated runtime-controller environment."""

    slug = models.SlugField(max_length=63, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default="")
    orchestrator = models.CharField(max_length=32, default="kubernetes", editable=False)
    enabled = models.BooleanField(default=False)
    capabilities = models.JSONField(default=default_runtime_capabilities)
    policy = models.JSONField(default=default_runtime_policy)
    revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ModuleRuntimeProfile(models.Model):
    """Reviewed, non-secret controller spec for one Kubernetes component."""

    module = models.OneToOneField(
        Module,
        on_delete=models.PROTECT,
        related_name="runtime_profile",
    )
    schema_version = models.PositiveSmallIntegerField(default=1)
    spec = models.JSONField(default=dict)
    spec_digest = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    revision = models.PositiveBigIntegerField(default=1)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("module__slug",)

    def __str__(self) -> str:
        return f"{self.module.slug}:runtime-v{self.schema_version}"


class RuntimeRelease(models.Model):
    """Immutable digest-pinned runtime snapshot for one catalog version."""

    application_version = models.OneToOneField(
        ApplicationVersion,
        on_delete=models.PROTECT,
        related_name="runtime_release",
    )
    manifest = models.JSONField()
    manifest_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.application_version}:sha256:{self.manifest_digest[:12]}"


class RuntimeDeployment(models.Model):
    """Desired and observed state for one application runtime environment."""

    class DesiredState(models.TextChoices):
        RUNNING = "running", _("Running")
        STOPPED = "stopped", _("Stopped")
        ABSENT = "absent", _("Absent")

    class ObservedState(models.TextChoices):
        PENDING = "pending", _("Pending")
        RECONCILING = "reconciling", _("Reconciling")
        RUNNING = "running", _("Running")
        DEGRADED = "degraded", _("Degraded")
        STOPPED = "stopped", _("Stopped")
        DELETING = "deleting", _("Deleting")
        DELETED = "deleted", _("Deleted")
        FAILED = "failed", _("Failed")
        UNKNOWN = "unknown", _("Unknown")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        HostedApplication,
        on_delete=models.PROTECT,
        related_name="runtime_deployments",
    )
    release = models.ForeignKey(
        RuntimeRelease,
        on_delete=models.PROTECT,
        related_name="deployments",
    )
    environment = models.ForeignKey(
        RuntimeEnvironment,
        on_delete=models.PROTECT,
        related_name="deployments",
    )
    desired_state = models.CharField(
        max_length=16,
        choices=DesiredState.choices,
        default=DesiredState.RUNNING,
    )
    observed_state = models.CharField(
        max_length=16,
        choices=ObservedState.choices,
        default=ObservedState.PENDING,
    )
    controller_id = models.CharField(max_length=128, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    secret_refs = models.JSONField(default=dict, blank=True)
    scaling = models.JSONField(default=dict, blank=True)
    generation = models.PositiveBigIntegerField(default=1)
    observed_generation = models.PositiveBigIntegerField(default=0)
    revision = models.PositiveBigIntegerField(default=1)
    last_error = models.CharField(max_length=500, blank=True, default="")
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_runtime_deployments",
    )
    created_by_label = models.CharField(max_length=255, blank=True, default="")
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("application__name", "environment__name")
        constraints = [
            models.UniqueConstraint(
                fields=("application", "environment"),
                condition=models.Q(deleted_at__isnull=True),
                name="hosting_runtime_unique_active_app_environment",
            ),
            models.UniqueConstraint(
                fields=("controller_id",),
                condition=~models.Q(controller_id=""),
                name="hosting_runtime_unique_controller_id",
            ),
            models.CheckConstraint(
                condition=models.Q(revision__gte=1),
                name="hosting_runtime_revision_positive",
            ),
        ]
        indexes = [
            models.Index(fields=("observed_state",), name="hosting_runtime_state_idx"),
        ]

    @property
    def version(self) -> str:
        return self.release.application_version.version

    def __str__(self) -> str:
        return f"{self.application.slug}:{self.environment_id}@{self.version}"


class RuntimeComponent(models.Model):
    deployment = models.ForeignKey(
        RuntimeDeployment,
        on_delete=models.CASCADE,
        related_name="components",
    )
    module_id = models.PositiveBigIntegerField()
    slug = models.SlugField(max_length=63)
    image_digest = models.CharField(max_length=255)
    desired_replicas = models.PositiveSmallIntegerField(default=1)
    ready_replicas = models.PositiveSmallIntegerField(default=0)
    available_replicas = models.PositiveSmallIntegerField(default=0)
    state = models.CharField(max_length=32, default="pending")
    health = models.CharField(max_length=32, default="unknown")
    restart_count = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("slug",)
        constraints = [
            models.UniqueConstraint(
                fields=("deployment", "slug"),
                name="hosting_runtime_unique_deployment_slug",
            )
        ]


class RuntimeOperation(models.Model):
    """Durable, leased and idempotent controller work item."""

    class OperationType(models.TextChoices):
        DEPLOY = "deploy", _("Deploy")
        CONFIGURE = "configure", _("Configure")
        START = "start", _("Start")
        STOP = "stop", _("Stop")
        RESTART = "restart", _("Restart")
        SCALE = "scale", _("Scale")
        UNDEPLOY = "undeploy", _("Undeploy")
        LOG_SNAPSHOT = "log_snapshot", _("Log snapshot")

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        RUNNING = "running", _("Running")
        SUCCEEDED = "succeeded", _("Succeeded")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deployment = models.ForeignKey(
        RuntimeDeployment,
        on_delete=models.PROTECT,
        related_name="operations",
    )
    operation_type = models.CharField(max_length=24, choices=OperationType.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    payload = models.JSONField(default=dict, blank=True)
    progress = models.JSONField(default=default_operation_progress)
    result = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_hash = models.CharField(max_length=64)
    target_generation = models.PositiveBigIntegerField(default=1)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runtime_operations",
    )
    actor_label = models.CharField(max_length=255, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    leased_by = models.CharField(max_length=128, blank=True, default="")
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-requested_at",)
        indexes = [
            models.Index(
                fields=("deployment", "-requested_at"),
                name="hosting_runtime_operation_idx",
            ),
            models.Index(
                fields=("status", "next_attempt_at"),
                name="hosting_runtime_queue_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.deployment_id}:{self.operation_type}:{self.status}"


class Dataset(models.Model):
    """Jeu de données accessible selon les droits utilisateur/groupe."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    modules = models.ManyToManyField(Module, related_name="datasets", blank=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="datasets",
        blank=True,
    )
    groups = models.ManyToManyField("auth.Group", related_name="datasets", blank=True)
    enabled = models.BooleanField(default=True)
    revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Dataset")
        verbose_name_plural = _("Datasets")

    def __str__(self) -> str:
        return self.name
