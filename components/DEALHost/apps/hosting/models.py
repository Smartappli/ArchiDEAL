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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Application version")
        verbose_name_plural = _("Application versions")
        unique_together = ("application", "version")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.application.slug}@{self.version}"


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Dataset")
        verbose_name_plural = _("Datasets")

    def __str__(self) -> str:
        return self.name
