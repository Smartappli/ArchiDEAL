from django.contrib import admin

from .models import (
    ApplicationVersion,
    Dataset,
    HostedApplication,
    Module,
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
