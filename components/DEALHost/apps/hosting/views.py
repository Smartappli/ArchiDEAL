import logging
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.db.models import Q
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsStaffOrAuthenticatedReadOnly
from apps.common.events import publish_event
from apps.common.events.subjects import (
    HOSTING_APPLICATION_CREATED,
    HOSTING_APPLICATION_DELETED,
    HOSTING_APPLICATION_UPDATED,
    HOSTING_APPLICATION_VERSION_RELEASED,
    HOSTING_MODULE_CREATED,
    HOSTING_MODULE_DELETED,
    HOSTING_MODULE_UPDATED,
    HOSTING_TOOL_CREATED,
    HOSTING_TOOL_DELETED,
    HOSTING_TOOL_UPDATED,
    HOSTING_TOOL_VERSION_RELEASED,
)

from .discovery import (
    auto_discover_tools_and_applications,
    public_autodiscovery_error,
)
from .models import Dataset, HostedApplication, Module, Tool
from .serializers import (
    ApplicationVersionSerializer,
    HostedApplicationSerializer,
    ModuleAttachSerializer,
    ModuleSerializer,
    ToolSerializer,
    ToolVersionSerializer,
    VersionCreateSerializer,
)

logger = logging.getLogger(__name__)


def _query_bool(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _report_error_count(report: object) -> int:
    error_count = getattr(report, "error_count", None)
    if isinstance(error_count, int):
        return error_count
    return len(getattr(report, "errors", None) or [])


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().order_by("name")
    serializer_class = ModuleSerializer
    permission_classes = [IsStaffOrAuthenticatedReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug", "branch", "source_path", "repository_name"]
    ordering_fields = ["name", "slug", "deployment_target", "created_at"]

    def get_queryset(self):  # type: ignore[override]
        queryset = super().get_queryset()
        enabled = self.request.query_params.get("enabled")
        repository = self.request.query_params.get("repository")
        repository_owner = self.request.query_params.get("repository_owner")
        repository_name = self.request.query_params.get("repository_name")
        deployment_target = self.request.query_params.get("deployment_target")
        has_public_route = self.request.query_params.get("has_public_route")
        if enabled is not None:
            queryset = queryset.filter(enabled=_query_bool(enabled))
        if repository:
            if "/" in repository:
                owner, name = repository.split("/", maxsplit=1)
                queryset = queryset.filter(
                    repository_owner=owner,
                    repository_name=name,
                )
            else:
                queryset = queryset.filter(repository_name=repository)
        if repository_owner:
            queryset = queryset.filter(repository_owner=repository_owner)
        if repository_name:
            queryset = queryset.filter(repository_name=repository_name)
        if deployment_target:
            queryset = queryset.filter(deployment_target=deployment_target)
        if has_public_route is not None:
            if _query_bool(has_public_route):
                queryset = queryset.exclude(public_path="").exclude(upstream_host="")
                queryset = queryset.filter(upstream_port__isnull=False)
            else:
                queryset = queryset.filter(
                    Q(public_path="")
                    | Q(upstream_host="")
                    | Q(upstream_port__isnull=True),
                )
        return queryset

    def perform_create(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_MODULE_CREATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
            },
            producer="apps.hosting.ModuleViewSet",
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_MODULE_UPDATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
            },
            producer="apps.hosting.ModuleViewSet",
        )

    def perform_destroy(self, instance):
        payload = {"id": instance.id, "slug": instance.slug}
        super().perform_destroy(instance)
        publish_event(
            event_type=HOSTING_MODULE_DELETED,
            data=payload,
            producer="apps.hosting.ModuleViewSet",
        )


class ToolViewSet(viewsets.ModelViewSet):
    queryset = (
        Tool.objects.prefetch_related("modules", "versions").all().order_by("name")
    )
    serializer_class = ToolSerializer
    permission_classes = [IsStaffOrAuthenticatedReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug", "description", "modules__slug", "current_version"]
    ordering_fields = ["name", "slug", "current_version", "created_at", "released_at"]

    def get_queryset(self):  # type: ignore[override]
        queryset = super().get_queryset()
        enabled = self.request.query_params.get("enabled")
        module_slug = self.request.query_params.get("module_slug")
        current_version = self.request.query_params.get("current_version")
        if enabled is not None:
            queryset = queryset.filter(enabled=enabled.lower() == "true")
        if module_slug:
            queryset = queryset.filter(modules__slug=module_slug)
        if current_version:
            queryset = queryset.filter(current_version=current_version)
        return queryset.distinct()

    def perform_create(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_TOOL_CREATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
            },
            producer="apps.hosting.ToolViewSet",
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_TOOL_UPDATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
            },
            producer="apps.hosting.ToolViewSet",
        )

    def perform_destroy(self, instance):
        payload = {"id": instance.id, "slug": instance.slug}
        super().perform_destroy(instance)
        publish_event(
            event_type=HOSTING_TOOL_DELETED,
            data=payload,
            producer="apps.hosting.ToolViewSet",
        )

    @action(detail=True, methods=["post"], url_path="attach-module")
    def attach_module(self, request: Request, pk: str | None = None) -> Response:
        serializer = ModuleAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool = self.get_object()
        tool.modules.add(serializer.validated_data["module"])
        return Response(self.get_serializer(tool).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="detach-module")
    def detach_module(self, request: Request, pk: str | None = None) -> Response:
        serializer = ModuleAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool = self.get_object()
        tool.modules.remove(serializer.validated_data["module"])
        return Response(self.get_serializer(tool).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="modules")
    def modules(self, request: Request, pk: str | None = None) -> Response:
        tool = self.get_object()
        return Response(
            ModuleSerializer(tool.modules.all(), many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get", "post"], url_path="versions")
    def versions(self, request: Request, pk: str | None = None) -> Response:
        tool = self.get_object()
        if request.method == "GET":
            data = ToolVersionSerializer(tool.versions.all(), many=True).data
            return Response(data, status=status.HTTP_200_OK)

        serializer = VersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool.current_version = serializer.validated_data["version"]
        tool.released_at = timezone.now()
        tool.save(update_fields=["current_version", "released_at", "updated_at"])
        version_obj, _ = tool.versions.update_or_create(
            version=serializer.validated_data["version"],
            defaults={
                "notes": serializer.validated_data.get("notes", ""),
                "source": serializer.validated_data.get("source", "manual"),
            },
        )
        publish_event(
            event_type=HOSTING_TOOL_VERSION_RELEASED,
            data={"id": tool.id, "slug": tool.slug, "version": version_obj.version},
            producer="apps.hosting.ToolViewSet",
        )
        return Response(
            ToolVersionSerializer(version_obj).data,
            status=status.HTTP_201_CREATED,
        )


class HostedApplicationViewSet(viewsets.ModelViewSet):
    queryset = (
        HostedApplication.objects.prefetch_related("modules", "versions")
        .all()
        .order_by("name")
    )
    serializer_class = HostedApplicationSerializer
    permission_classes = [IsStaffOrAuthenticatedReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug", "description", "modules__slug", "current_version"]
    ordering_fields = ["name", "slug", "current_version", "created_at", "released_at"]

    def get_queryset(self):  # type: ignore[override]
        queryset = super().get_queryset()
        enabled = self.request.query_params.get("enabled")
        module_slug = self.request.query_params.get("module_slug")
        current_version = self.request.query_params.get("current_version")
        if enabled is not None:
            queryset = queryset.filter(enabled=enabled.lower() == "true")
        if module_slug:
            queryset = queryset.filter(modules__slug=module_slug)
        if current_version:
            queryset = queryset.filter(current_version=current_version)
        return queryset.distinct()

    def perform_create(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_APPLICATION_CREATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
            },
            producer="apps.hosting.HostedApplicationViewSet",
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_APPLICATION_UPDATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
            },
            producer="apps.hosting.HostedApplicationViewSet",
        )

    def perform_destroy(self, instance):
        payload = {"id": instance.id, "slug": instance.slug}
        super().perform_destroy(instance)
        publish_event(
            event_type=HOSTING_APPLICATION_DELETED,
            data=payload,
            producer="apps.hosting.HostedApplicationViewSet",
        )

    @action(detail=True, methods=["post"], url_path="attach-module")
    def attach_module(self, request: Request, pk: str | None = None) -> Response:
        serializer = ModuleAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = self.get_object()
        application.modules.add(serializer.validated_data["module"])
        return Response(
            self.get_serializer(application).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="detach-module")
    def detach_module(self, request: Request, pk: str | None = None) -> Response:
        serializer = ModuleAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = self.get_object()
        application.modules.remove(serializer.validated_data["module"])
        return Response(
            self.get_serializer(application).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="modules")
    def modules(self, request: Request, pk: str | None = None) -> Response:
        application = self.get_object()
        return Response(
            ModuleSerializer(application.modules.all(), many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get", "post"], url_path="versions")
    def versions(self, request: Request, pk: str | None = None) -> Response:
        application = self.get_object()
        if request.method == "GET":
            data = ApplicationVersionSerializer(
                application.versions.all(),
                many=True,
            ).data
            return Response(data, status=status.HTTP_200_OK)

        serializer = VersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application.current_version = serializer.validated_data["version"]
        application.released_at = timezone.now()
        application.save(update_fields=["current_version", "released_at", "updated_at"])
        version_obj, _ = application.versions.update_or_create(
            version=serializer.validated_data["version"],
            defaults={
                "notes": serializer.validated_data.get("notes", ""),
                "source": serializer.validated_data.get("source", "manual"),
            },
        )
        publish_event(
            event_type=HOSTING_APPLICATION_VERSION_RELEASED,
            data={
                "id": application.id,
                "slug": application.slug,
                "version": version_obj.version,
            },
            producer="apps.hosting.HostedApplicationViewSet",
        )
        return Response(
            ApplicationVersionSerializer(version_obj).data,
            status=status.HTTP_201_CREATED,
        )


class AutoDiscoverView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request: Request) -> Response:
        report = auto_discover_tools_and_applications()
        if report.errors:
            logger.warning(
                "Hosting autodiscovery failed with %d error(s)",
                _report_error_count(report),
            )
        return Response(
            report.to_dict(include_errors=False),
            status=status.HTTP_200_OK,
        )


class ManagementInterfaceView(LoginRequiredMixin, TemplateView):
    template_name = "hosting/manage.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["modules"] = Module.objects.all().order_by("name")
        context["tools"] = (
            Tool.objects.prefetch_related("modules").all().order_by("name")
        )
        context["applications"] = (
            HostedApplication.objects.prefetch_related("modules").all().order_by("name")
        )

        user = self.request.user
        datasets = Dataset.objects.prefetch_related("modules").filter(enabled=True)
        if not user.is_superuser:
            datasets = datasets.filter(
                Q(users=user) | Q(groups__in=user.groups.all()),
            ).distinct()
        context["datasets"] = datasets.order_by("name")
        return context


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self) -> bool:
        return bool(self.request.user.is_staff)


class ManagementAutoDiscoverView(StaffRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        manifests_dir = Path(settings.BASE_DIR) / "manifests"
        report = auto_discover_tools_and_applications(manifests_dir=manifests_dir)
        if report.errors:
            logger.warning(
                "Hosting management autodiscovery failed with %d error(s)",
                _report_error_count(report),
            )
            messages.error(request, _("Autodiscovery failed; no changes were applied."))
            messages.error(request, public_autodiscovery_error())
        else:
            messages.success(
                request,
                (
                    _("Autodiscovery completed: ")
                    + _(
                        "tools created=%(tools_created)s, tools updated=%(tools_updated)s, "
                        "modules created=%(modules_created)s, modules updated=%(modules_updated)s, "
                        "apps created=%(apps_created)s, apps updated=%(apps_updated)s, "
                        "tool versions created=%(tool_versions_created)s, "
                        "application versions created=%(application_versions_created)s.",
                    )
                    % {
                        "modules_created": report.modules_created,
                        "modules_updated": report.modules_updated,
                        "tools_created": report.tools_created,
                        "tools_updated": report.tools_updated,
                        "apps_created": report.applications_created,
                        "apps_updated": report.applications_updated,
                        "tool_versions_created": report.tool_versions_created,
                        "application_versions_created": report.application_versions_created,
                    }
                ),
            )
        return redirect("hosting-management")
