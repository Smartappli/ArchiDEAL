import logging
import re
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
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
    HOSTING_DATASET_CREATED,
    HOSTING_DATASET_DELETED,
    HOSTING_DATASET_UPDATED,
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
    DatasetAdminSerializer,
    DatasetPrincipalGroupSerializer,
    DatasetPrincipalUserSerializer,
    DatasetSerializer,
    HostedApplicationSerializer,
    ModuleAttachSerializer,
    ModuleSerializer,
    ToolSerializer,
    ToolVersionSerializer,
    VersionCreateSerializer,
)
from .versioning import (
    VersionMetadataConflict,
    VersionRevisionConflict,
    publish_immutable_version,
)

logger = logging.getLogger(__name__)


def _query_bool(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _if_match_revision(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r'"([1-9][0-9]*)"', value.strip())
    if match is None:
        raise ValueError('If-Match must contain a strong revision ETag such as "3".')
    return int(match.group(1))


def _revision_etag(revision: int) -> str:
    return f'"{revision}"'


def _report_error_count(report: object) -> int:
    error_count = getattr(report, "error_count", None)
    if isinstance(error_count, int):
        return error_count
    return len(getattr(report, "errors", None) or [])


def _immutable_version_conflict(version: str) -> Response:
    return Response(
        {
            "code": "version_conflict",
            "detail": (
                f"Version {version} already exists with different immutable "
                "release metadata."
            ),
        },
        status=status.HTTP_409_CONFLICT,
    )


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().order_by("name")
    serializer_class = ModuleSerializer
    permission_classes = [IsStaffOrAuthenticatedReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug", "branch", "source_path", "repository_name"]
    ordering_fields = ["name", "slug", "deployment_target", "created_at"]

    @staticmethod
    def _has_revocation_sensitive_route(module: Module) -> bool:
        return bool(
            module.public_path.strip()
            and module.upstream_host.strip()
            and module.upstream_port is not None
        )

    @staticmethod
    def _route_revocation_unavailable() -> Response:
        return Response(
            {
                "code": "route_revocation_unavailable",
                "detail": (
                    "This module has routable metadata and may already own a dynamic "
                    "APISIX route. Disabling, deleting, renaming or retargeting it is "
                    "blocked until audited route revocation is implemented."
                ),
            },
            status=status.HTTP_409_CONFLICT,
        )

    @staticmethod
    def _requests_route_revocation(module: Module, data: object) -> bool:
        if not hasattr(data, "get") or not hasattr(data, "__contains__"):
            return False

        if "enabled" in data:
            requested_enabled = data.get("enabled")
            if requested_enabled is False or (
                isinstance(requested_enabled, str)
                and requested_enabled.strip().casefold() in {"0", "false", "no", "off"}
            ):
                return True

        for field in ("slug", "public_path", "upstream_host"):
            if field in data and str(data.get(field)) != str(getattr(module, field)):
                return True
        if "upstream_port" in data:
            try:
                requested_port = int(data.get("upstream_port"))
            except (TypeError, ValueError):
                return False
            if requested_port != module.upstream_port:
                return True
        return False

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

    def update(self, request: Request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs[lookup_url_kwarg]
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            module = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, module)
            if self._has_revocation_sensitive_route(
                module,
            ) and self._requests_route_revocation(module, request.data):
                return self._route_revocation_unavailable()

            serializer = self.get_serializer(
                module,
                data=request.data,
                partial=partial,
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            if getattr(module, "_prefetched_objects_cache", None):
                module._prefetched_objects_cache = {}
            return Response(serializer.data)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs[lookup_url_kwarg]
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            module = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, module)
            if self._has_revocation_sensitive_route(module):
                return self._route_revocation_unavailable()
            self.perform_destroy(module)
            return Response(status=status.HTTP_204_NO_CONTENT)

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
        try:
            publication = publish_immutable_version(tool, serializer.validated_data)
        except VersionMetadataConflict as exc:
            return _immutable_version_conflict(str(exc))
        if publication.created:
            publish_event(
                event_type=HOSTING_TOOL_VERSION_RELEASED,
                data={
                    "id": publication.resource.id,
                    "slug": publication.resource.slug,
                    "version": publication.version.version,
                },
                producer="apps.hosting.ToolViewSet",
            )
        return Response(
            ToolVersionSerializer(publication.version).data,
            status=(
                status.HTTP_201_CREATED if publication.created else status.HTTP_200_OK
            ),
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

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        response = super().retrieve(request, *args, **kwargs)
        response["ETag"] = _revision_etag(response.data["revision"])
        return response

    def update(self, request: Request, *args, **kwargs) -> Response:
        try:
            expected_revision = _if_match_revision(request.headers.get("If-Match"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if expected_revision is None:
            return Response(
                {"detail": "If-Match is required for application updates."},
                status=428,
            )

        partial = kwargs.pop("partial", False)
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs[lookup_url_kwarg]
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            instance = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, instance)
            if instance.revision != expected_revision:
                return self._stale_revision_response(instance)

            serializer = self.get_serializer(
                instance,
                data=request.data,
                partial=partial,
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            if getattr(instance, "_prefetched_objects_cache", None):
                instance._prefetched_objects_cache = {}
            response = Response(serializer.data)
            response["ETag"] = _revision_etag(serializer.instance.revision)
            return response

    @staticmethod
    def _stale_revision_response(application: HostedApplication) -> Response:
        response = Response(
            {
                "detail": "The application changed after it was loaded.",
                "revision": application.revision,
            },
            status=status.HTTP_412_PRECONDITION_FAILED,
        )
        response["ETag"] = _revision_etag(application.revision)
        return response

    def perform_create(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_APPLICATION_CREATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
                "revision": instance.revision,
            },
            producer="apps.hosting.HostedApplicationViewSet",
        )

    def perform_update(self, serializer):
        next_revision = serializer.instance.revision + 1
        instance = serializer.save(revision=next_revision)
        publish_event(
            event_type=HOSTING_APPLICATION_UPDATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
                "revision": instance.revision,
            },
            producer="apps.hosting.HostedApplicationViewSet",
        )

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        try:
            expected_revision = _if_match_revision(request.headers.get("If-Match"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if expected_revision is None:
            return Response(
                {"detail": "If-Match is required for application deletion."},
                status=428,
            )

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs[lookup_url_kwarg]
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            instance = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, instance)
            if instance.revision != expected_revision:
                return self._stale_revision_response(instance)
            self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        payload = {
            "id": instance.id,
            "slug": instance.slug,
            "revision": instance.revision,
        }
        super().perform_destroy(instance)
        publish_event(
            event_type=HOSTING_APPLICATION_DELETED,
            data=payload,
            producer="apps.hosting.HostedApplicationViewSet",
        )

    @action(detail=True, methods=["post"], url_path="attach-module")
    def attach_module(self, request: Request, pk: str | None = None) -> Response:
        return self._update_module_membership(
            request,
            pk=pk,
            attach=True,
        )

    @action(detail=True, methods=["post"], url_path="detach-module")
    def detach_module(self, request: Request, pk: str | None = None) -> Response:
        return self._update_module_membership(
            request,
            pk=pk,
            attach=False,
        )

    def _update_module_membership(
        self,
        request: Request,
        *,
        pk: str | None,
        attach: bool,
    ) -> Response:
        serializer = ModuleAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expected_revision = _if_match_revision(request.headers.get("If-Match"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if expected_revision is None:
            return Response(
                {"detail": "If-Match is required for application module changes."},
                status=428,
            )

        lookup_value = pk if pk is not None else self.kwargs.get(self.lookup_field)
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            application = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, application)
            if application.revision != expected_revision:
                return self._stale_revision_response(application)

            module = serializer.validated_data["module"]
            is_attached = application.modules.filter(pk=module.pk).exists()
            changed = (attach and not is_attached) or (not attach and is_attached)
            if changed:
                if attach:
                    application.modules.add(module)
                else:
                    application.modules.remove(module)
                application.revision += 1
                application.save(update_fields=["revision", "updated_at"])
                publish_event(
                    event_type=HOSTING_APPLICATION_UPDATED,
                    data={
                        "id": application.id,
                        "slug": application.slug,
                        "enabled": application.enabled,
                        "revision": application.revision,
                        "module_slug": module.slug,
                    },
                    producer="apps.hosting.HostedApplicationViewSet",
                )

            if getattr(application, "_prefetched_objects_cache", None):
                application._prefetched_objects_cache = {}
            response = Response(
                self.get_serializer(application).data,
                status=status.HTTP_200_OK,
            )
            response["ETag"] = _revision_etag(application.revision)
            return response

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

        try:
            expected_revision = _if_match_revision(request.headers.get("If-Match"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if expected_revision is None:
            return Response(
                {"detail": "If-Match is required for application version publication."},
                status=428,
            )

        serializer = VersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            publication = publish_immutable_version(
                application,
                serializer.validated_data,
                expected_revision=expected_revision,
            )
        except VersionRevisionConflict as exc:
            return self._stale_revision_response(exc.resource)
        except VersionMetadataConflict as exc:
            return _immutable_version_conflict(str(exc))
        if publication.created:
            publish_event(
                event_type=HOSTING_APPLICATION_VERSION_RELEASED,
                data={
                    "id": publication.resource.id,
                    "slug": publication.resource.slug,
                    "version": publication.version.version,
                    "revision": publication.resource.revision,
                },
                producer="apps.hosting.HostedApplicationViewSet",
            )
        response = Response(
            ApplicationVersionSerializer(publication.version).data,
            status=(
                status.HTTP_201_CREATED if publication.created else status.HTTP_200_OK
            ),
        )
        response["ETag"] = _revision_etag(publication.resource.revision)
        return response


class DatasetViewSet(viewsets.ModelViewSet):
    """Manage datasets while enforcing their user and group access lists."""

    queryset = (
        Dataset.objects.prefetch_related("modules", "users", "groups")
        .all()
        .order_by("name")
    )
    permission_classes = [IsStaffOrAuthenticatedReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug", "description", "modules__slug"]
    ordering_fields = ["name", "slug", "enabled", "created_at"]

    def get_serializer_class(self):
        if self.request.user.is_staff:
            return DatasetAdminSerializer
        return DatasetSerializer

    def get_queryset(self):  # type: ignore[override]
        queryset = super().get_queryset()
        user = self.request.user

        if not user.is_staff:
            acl_user = user if getattr(user, "pk", None) is not None else None
            if acl_user is None:
                username = str(
                    getattr(user, "acl_username", None) or getattr(user, "username", "")
                ).strip()
                acl_user = (
                    get_user_model()
                    .objects.filter(username=username, is_active=True)
                    .first()
                    if username
                    else None
                )
            external_groups = tuple(
                str(value)
                for value in getattr(user, "oidc_groups", ())
                if str(value).strip()
            )
            access_scope = None
            if acl_user is not None:
                access_scope = Q(users=acl_user) | Q(groups__in=acl_user.groups.all())
            if external_groups:
                group_scope = Q(groups__name__in=external_groups)
                access_scope = (
                    group_scope if access_scope is None else access_scope | group_scope
                )
            if access_scope is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(enabled=True).filter(access_scope)

        enabled = self.request.query_params.get("enabled")
        module_slug = self.request.query_params.get("module_slug")
        if enabled is not None:
            queryset = queryset.filter(enabled=_query_bool(enabled))
        if module_slug:
            queryset = queryset.filter(modules__slug=module_slug)

        # ACL-oriented filters are administrative: exposing them to ordinary
        # readers would make it possible to infer another user's membership.
        if user.is_staff:
            user_id = self.request.query_params.get("user_id")
            group_id = self.request.query_params.get("group_id")
            if user_id:
                queryset = queryset.filter(users__id=user_id)
            if group_id:
                queryset = queryset.filter(groups__id=group_id)

        return queryset.distinct()

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        response = super().retrieve(request, *args, **kwargs)
        response["ETag"] = f'"{response.data["revision"]}"'
        return response

    def update(self, request: Request, *args, **kwargs) -> Response:
        try:
            expected_revision = _if_match_revision(request.headers.get("If-Match"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if expected_revision is None:
            return Response(
                {"detail": "If-Match is required for dataset updates."},
                status=428,
            )

        partial = kwargs.pop("partial", False)
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs[lookup_url_kwarg]
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            instance = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, instance)
            if instance.revision != expected_revision:
                response = Response(
                    {
                        "detail": "The dataset changed after it was loaded.",
                        "revision": instance.revision,
                    },
                    status=status.HTTP_412_PRECONDITION_FAILED,
                )
                response["ETag"] = f'"{instance.revision}"'
                return response

            serializer = self.get_serializer(
                instance, data=request.data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            if getattr(instance, "_prefetched_objects_cache", None):
                instance._prefetched_objects_cache = {}
            response = Response(serializer.data)
            response["ETag"] = f'"{serializer.instance.revision}"'
            return response

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Delete only the exact dataset revision confirmed by the operator."""
        try:
            expected_revision = _if_match_revision(request.headers.get("If-Match"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if expected_revision is None:
            return Response(
                {"detail": "If-Match is required for dataset deletion."},
                status=428,
            )

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs[lookup_url_kwarg]
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset()).select_for_update()
            instance = get_object_or_404(
                queryset,
                **{self.lookup_field: lookup_value},
            )
            self.check_object_permissions(request, instance)
            if instance.revision != expected_revision:
                response = Response(
                    {
                        "detail": "The dataset changed after it was loaded.",
                        "revision": instance.revision,
                    },
                    status=status.HTTP_412_PRECONDITION_FAILED,
                )
                response["ETag"] = f'"{instance.revision}"'
                return response

            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        instance = serializer.save()
        publish_event(
            event_type=HOSTING_DATASET_CREATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
                "revision": instance.revision,
                "actor": str(
                    getattr(
                        self.request.user, "acl_username", self.request.user.username
                    )
                ),
            },
            producer="apps.hosting.DatasetViewSet",
        )

    def perform_update(self, serializer):
        next_revision = serializer.instance.revision + 1
        instance = serializer.save(revision=next_revision)
        publish_event(
            event_type=HOSTING_DATASET_UPDATED,
            data={
                "id": instance.id,
                "slug": instance.slug,
                "enabled": instance.enabled,
                "revision": instance.revision,
                "actor": str(
                    getattr(
                        self.request.user, "acl_username", self.request.user.username
                    )
                ),
            },
            producer="apps.hosting.DatasetViewSet",
        )

    def perform_destroy(self, instance):
        payload = {
            "id": instance.id,
            "slug": instance.slug,
            "revision": instance.revision,
            "actor": str(
                getattr(self.request.user, "acl_username", self.request.user.username)
            ),
        }
        super().perform_destroy(instance)
        publish_event(
            event_type=HOSTING_DATASET_DELETED,
            data=payload,
            producer="apps.hosting.DatasetViewSet",
        )


class DatasetPrincipalListView(APIView):
    """Return only the principals needed by staff dataset ACL editors."""

    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        users = (
            get_user_model()
            .objects.select_related("oidc_acl_identity")
            .all()
            .order_by("id")
        )
        groups = Group.objects.only("id", "name").all().order_by("name")
        response = Response(
            {
                "users": DatasetPrincipalUserSerializer(users, many=True).data,
                "groups": DatasetPrincipalGroupSerializer(groups, many=True).data,
                "can_provision_oidc": bool(request.user.is_superuser),
            }
        )
        response["Cache-Control"] = "private, no-store"
        return response


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
