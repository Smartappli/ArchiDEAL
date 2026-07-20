from django.contrib import admin

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
    RuntimeRelease,
    Tool,
    ToolVersion,
)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "deployment_target",
        "public_path",
        "upstream_host",
        "upstream_port",
        "enabled",
        "created_at",
    )
    list_filter = ("enabled", "branch", "deployment_target", "repository_owner")
    search_fields = ("name", "slug", "image", "source_path", "repository_name")


class ToolVersionInline(admin.TabularInline):
    model = ToolVersion
    extra = 0
    fields = ("version", "source", "notes", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "current_version",
        "released_at",
        "enabled",
        "created_at",
    )
    list_filter = ("enabled", "current_version")
    search_fields = ("name", "slug", "description", "current_version")
    filter_horizontal = ("modules",)
    inlines = [ToolVersionInline]


class ApplicationVersionInline(admin.TabularInline):
    model = ApplicationVersion
    extra = 0
    fields = ("version", "source", "notes", "created_at")
    readonly_fields = ("created_at",)


@admin.register(HostedApplication)
class HostedApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "current_version",
        "released_at",
        "enabled",
        "created_at",
    )
    list_filter = ("enabled", "current_version")
    search_fields = ("name", "slug", "description", "current_version")
    filter_horizontal = ("modules",)
    inlines = [ApplicationVersionInline]


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "enabled", "created_at")
    list_filter = ("enabled",)
    search_fields = ("name", "slug", "description")
    filter_horizontal = ("modules", "users", "groups")


@admin.register(RuntimeEnvironment)
class RuntimeEnvironmentAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "orchestrator", "enabled", "revision", "updated_at")
    list_filter = ("enabled", "orchestrator")
    search_fields = ("name", "slug", "description")


@admin.register(ModuleRuntimeProfile)
class ModuleRuntimeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "module",
        "schema_version",
        "enabled",
        "verified_at",
        "revision",
        "updated_at",
    )
    list_filter = ("enabled", "schema_version")
    search_fields = ("module__name", "module__slug", "spec_digest")
    readonly_fields = ("created_at", "updated_at")


class ImmutableRuntimeAdminMixin:
    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(RuntimeRelease)
class RuntimeReleaseAdmin(ImmutableRuntimeAdminMixin, admin.ModelAdmin):
    list_display = ("application_version", "manifest_digest", "created_at")
    search_fields = (
        "application_version__application__name",
        "application_version__application__slug",
        "application_version__version",
        "manifest_digest",
    )
    readonly_fields = (
        "application_version",
        "manifest",
        "manifest_digest",
        "created_at",
    )


class RuntimeComponentInline(admin.TabularInline):
    model = RuntimeComponent
    extra = 0
    readonly_fields = (
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
        "updated_at",
    )
    can_delete = False


@admin.register(RuntimeDeployment)
class RuntimeDeploymentAdmin(ImmutableRuntimeAdminMixin, admin.ModelAdmin):
    list_display = (
        "application",
        "environment",
        "version",
        "desired_state",
        "observed_state",
        "generation",
        "revision",
        "updated_at",
    )
    list_filter = ("environment", "desired_state", "observed_state")
    search_fields = ("application__name", "application__slug", "controller_id")
    readonly_fields = [field.name for field in RuntimeDeployment._meta.fields]
    inlines = [RuntimeComponentInline]


@admin.register(RuntimeOperation)
class RuntimeOperationAdmin(ImmutableRuntimeAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "deployment",
        "operation_type",
        "status",
        "attempts",
        "controller_failures",
        "requested_at",
        "finished_at",
    )
    list_filter = ("operation_type", "status")
    search_fields = ("id", "deployment__application__slug", "actor_label")
    readonly_fields = [field.name for field in RuntimeOperation._meta.fields]
