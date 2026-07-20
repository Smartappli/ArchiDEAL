from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from .models import (
    HostedApplication,
    RuntimeComponent,
    RuntimeDeployment,
    RuntimeEnvironment,
    RuntimeOperation,
)
from .runtime_release import RuntimeReleaseNotDeployable, runtime_release_for
from .serializers import (
    RuntimeActionSerializer,
    RuntimeDeploymentCreateSerializer,
    RuntimeDeploymentSerializer,
    RuntimeDeploymentUpdateSerializer,
    RuntimeEnvironmentSerializer,
    RuntimeLogRequestSerializer,
    RuntimeOperationSerializer,
)


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class RuntimePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class RuntimeEnvironmentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = RuntimeEnvironment.objects.all().order_by("name")
    serializer_class = RuntimeEnvironmentSerializer
    permission_classes = [IsAdminUser]
    pagination_class = RuntimePagination
    lookup_field = "slug"


class RuntimeOperationViewSet(
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = RuntimeOperation.objects.select_related("deployment").all()
    serializer_class = RuntimeOperationSerializer
    permission_classes = [IsAdminUser]

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        response = super().retrieve(request, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class RuntimeDeploymentViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdminUser]
    pagination_class = RuntimePagination

    def get_queryset(self):  # type: ignore[override]
        queryset = RuntimeDeployment.objects.select_related(
            "application",
            "release__application_version",
            "environment",
        ).prefetch_related("components__module")
        application_id = self.request.query_params.get("application_id")
        environment = self.request.query_params.get("environment")
        observed_state = self.request.query_params.get("observed_state")
        if application_id:
            queryset = queryset.filter(application_id=application_id)
        if environment:
            queryset = queryset.filter(environment_id=environment)
        if observed_state:
            queryset = queryset.filter(observed_state=observed_state)
        return queryset.order_by(
            "application__name", "environment__name", "-created_at"
        )

    def list(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        serializer = RuntimeDeploymentSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        deployment = self.get_object()
        response = Response(RuntimeDeploymentSerializer(deployment).data)
        response["ETag"] = _etag(deployment.revision)
        response["Cache-Control"] = "private, no-store"
        return response

    def create(self, request: Request) -> Response:
        serializer = RuntimeDeploymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.validated_data["application"]
        environment = serializer.validated_data["environment"]
        normalized = {
            "application_id": application.id,
            "environment": environment.slug,
            "version": serializer.validated_data["version"],
            "configuration": serializer.validated_data["configuration"],
            "secret_refs": serializer.validated_data["secret_refs"],
            "scaling": serializer.validated_data["scaling"],
        }
        request_hash = _request_hash("create", normalized)
        replay = self._replay(request, request_hash)
        if replay is not None:
            return replay
        unavailable = _runtime_unavailable()
        if unavailable is not None:
            return unavailable
        revision_response = _application_precondition(request, application)
        if revision_response is not None:
            return revision_response

        try:
            with transaction.atomic():
                locked_application = HostedApplication.objects.select_for_update().get(
                    pk=application.pk
                )
                revision_response = _application_precondition(
                    request,
                    locked_application,
                )
                if revision_response is not None:
                    return revision_response
                if RuntimeDeployment.objects.filter(
                    application=locked_application,
                    environment=environment,
                    deleted_at__isnull=True,
                ).exists():
                    return _problem(
                        "This application already has an active deployment in that environment.",
                        code="deployment_exists",
                        status_code=status.HTTP_409_CONFLICT,
                    )
                try:
                    release = runtime_release_for(
                        locked_application,
                        serializer.validated_data["version"],
                        environment,
                    )
                except RuntimeReleaseNotDeployable as exc:
                    return _problem(
                        str(exc),
                        code=exc.code,
                        status_code=status.HTTP_409_CONFLICT,
                    )
                actor, actor_label = _actor(request)
                deployment = RuntimeDeployment.objects.create(
                    application=locked_application,
                    release=release,
                    environment=environment,
                    observed_state=RuntimeDeployment.ObservedState.PENDING,
                    configuration=serializer.validated_data["configuration"],
                    secret_refs=serializer.validated_data["secret_refs"],
                    scaling=serializer.validated_data["scaling"],
                    created_by=actor,
                    created_by_label=actor_label,
                )
                self._create_components(deployment)
                operation = _create_operation(
                    request,
                    deployment,
                    RuntimeOperation.OperationType.DEPLOY,
                    request_hash,
                    payload={},
                )
        except IntegrityError:
            return _problem(
                "The deployment or idempotency key already exists.",
                code="runtime_conflict",
                status_code=status.HTTP_409_CONFLICT,
            )
        return _mutation_response(deployment, operation, status.HTTP_202_ACCEPTED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        deployment = self.get_object()
        serializer = RuntimeDeploymentUpdateSerializer(
            data=request.data,
            partial=True,
            context={"deployment": deployment},
        )
        serializer.is_valid(raise_exception=True)
        request_hash = _request_hash(
            f"configure:{deployment.id}", serializer.validated_data
        )
        replay = self._replay(request, request_hash)
        if replay is not None:
            return replay
        unavailable = _runtime_unavailable()
        if unavailable is not None:
            return unavailable
        with transaction.atomic():
            locked = self._locked_deployment(deployment.pk)
            precondition = _deployment_precondition(request, locked)
            if precondition is not None:
                return precondition
            busy = _busy_response(locked)
            if busy is not None:
                return busy
            if locked.deleted_at is not None:
                return _problem(
                    "A deleted deployment cannot be configured.",
                    code="deployment_deleted",
                    status_code=status.HTTP_409_CONFLICT,
                )
            for field, value in serializer.validated_data.items():
                setattr(locked, field, value)
            locked.generation += 1
            locked.revision += 1
            locked.observed_state = RuntimeDeployment.ObservedState.RECONCILING
            locked.last_error = ""
            locked.save()
            self._sync_component_scaling(locked)
            operation_type = (
                RuntimeOperation.OperationType.CONFIGURE
                if locked.controller_id
                else RuntimeOperation.OperationType.DEPLOY
            )
            operation = _create_operation(
                request,
                locked,
                operation_type,
                request_hash,
                payload={"changed_fields": sorted(serializer.validated_data)},
            )
        return _mutation_response(
            self._fresh(locked.pk), operation, status.HTTP_202_ACCEPTED
        )

    update = partial_update

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        deployment = self.get_object()
        request_hash = _request_hash(f"undeploy:{deployment.id}", {})
        replay = self._replay(request, request_hash)
        if replay is not None:
            return replay
        unavailable = _runtime_unavailable()
        if unavailable is not None:
            return unavailable
        with transaction.atomic():
            locked = self._locked_deployment(deployment.pk)
            precondition = _deployment_precondition(request, locked)
            if precondition is not None:
                return precondition
            busy = _busy_response(locked)
            if busy is not None:
                return busy
            if locked.deleted_at is not None:
                return _problem(
                    "The deployment is already deleted.",
                    code="deployment_deleted",
                    status_code=status.HTTP_409_CONFLICT,
                )
            locked.desired_state = RuntimeDeployment.DesiredState.ABSENT
            locked.observed_state = RuntimeDeployment.ObservedState.DELETING
            locked.generation += 1
            locked.revision += 1
            locked.last_error = ""
            locked.save()
            operation = _create_operation(
                request,
                locked,
                RuntimeOperation.OperationType.UNDEPLOY,
                request_hash,
                payload={},
            )
        return _mutation_response(
            self._fresh(locked.pk), operation, status.HTTP_202_ACCEPTED
        )

    @action(detail=True, methods=["post"], url_path="actions")
    def actions(self, request: Request, pk: str | None = None) -> Response:
        deployment = self.get_object()
        serializer = RuntimeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        normalized = dict(serializer.validated_data)
        request_hash = _request_hash(f"action:{deployment.id}", normalized)
        replay = self._replay(request, request_hash)
        if replay is not None:
            return replay
        unavailable = _runtime_unavailable()
        if unavailable is not None:
            return unavailable
        action_name = serializer.validated_data["action"]
        with transaction.atomic():
            locked = self._locked_deployment(deployment.pk)
            precondition = _deployment_precondition(request, locked)
            if precondition is not None:
                return precondition
            busy = _busy_response(locked)
            if busy is not None:
                return busy
            transition_error = _validate_transition(locked, action_name)
            if transition_error is not None:
                return transition_error
            if not locked.controller_id and action_name != "start":
                return _problem(
                    "Retry the deployment before requesting this action.",
                    code="runtime_identity_unavailable",
                    status_code=status.HTTP_409_CONFLICT,
                )
            operation_type = (
                RuntimeOperation.OperationType.DEPLOY
                if action_name == "start" and not locked.controller_id
                else action_name
            )
            payload: dict[str, Any] = {}
            if action_name == "start":
                locked.desired_state = RuntimeDeployment.DesiredState.RUNNING
            elif action_name == "stop":
                locked.desired_state = RuntimeDeployment.DesiredState.STOPPED
            elif action_name == "scale":
                component_slug = serializer.validated_data["component"]
                replicas = serializer.validated_data["replicas"]
                component = (
                    locked.components.select_related("module")
                    .filter(module__slug=component_slug)
                    .first()
                )
                if component is None:
                    return _problem(
                        "The requested component is not part of the deployment.",
                        code="component_not_found",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                scaling = dict(locked.scaling)
                scaling[component_slug] = {"mode": "fixed", "replicas": replicas}
                locked.scaling = scaling
                component.desired_replicas = replicas
                component.save(update_fields=["desired_replicas", "updated_at"])
                payload = {"component": component_slug, "replicas": replicas}
            locked.observed_state = RuntimeDeployment.ObservedState.RECONCILING
            locked.generation += 1
            locked.revision += 1
            locked.last_error = ""
            locked.save()
            operation = _create_operation(
                request,
                locked,
                operation_type,
                request_hash,
                payload=payload,
            )
        return _mutation_response(
            self._fresh(locked.pk), operation, status.HTTP_202_ACCEPTED
        )

    @action(detail=True, methods=["get"], url_path="operations")
    def operations(self, request: Request, pk: str | None = None) -> Response:
        deployment = self.get_object()
        queryset = deployment.operations.all().order_by("-requested_at")
        page = self.paginate_queryset(queryset)
        serializer = RuntimeOperationSerializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response["Cache-Control"] = "private, no-store"
        return response

    @action(detail=True, methods=["post"], url_path="log-requests")
    def log_requests(self, request: Request, pk: str | None = None) -> Response:
        deployment = self.get_object()
        serializer = RuntimeLogRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        normalized = dict(serializer.validated_data)
        request_hash = _request_hash(f"logs:{deployment.id}", normalized)
        replay = self._replay_operation(request, request_hash)
        if replay is not None:
            return replay
        unavailable = _runtime_unavailable()
        if unavailable is not None:
            return unavailable
        with transaction.atomic():
            locked = self._locked_deployment(deployment.pk)
            precondition = _deployment_precondition(request, locked)
            if precondition is not None:
                return precondition
            if not locked.controller_id:
                return _problem(
                    "Logs are unavailable until the deployment has a runtime identity.",
                    code="runtime_identity_unavailable",
                    status_code=status.HTTP_409_CONFLICT,
                )
            if not locked.components.filter(
                module__slug=serializer.validated_data["component"]
            ).exists():
                return _problem(
                    "The requested log component is not part of the deployment.",
                    code="component_not_found",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            capabilities = locked.environment.capabilities
            log_limits = (
                capabilities.get("logs", {}) if isinstance(capabilities, dict) else {}
            )
            maximum = (
                log_limits.get("max_lines", 1000)
                if isinstance(log_limits, dict)
                else 1000
            )
            if serializer.validated_data["tail_lines"] > maximum:
                return _problem(
                    "The requested log tail exceeds the environment limit.",
                    code="log_limit_exceeded",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            operation = _create_operation(
                request,
                locked,
                RuntimeOperation.OperationType.LOG_SNAPSHOT,
                request_hash,
                payload=normalized,
            )
        response = Response(
            RuntimeOperationSerializer(operation).data,
            status=status.HTTP_202_ACCEPTED,
        )
        response["Cache-Control"] = "private, no-store"
        return response

    def _replay(self, request: Request, request_hash: str) -> Response | None:
        operation, error = _idempotency_replay(request, request_hash)
        if error is not None:
            return error
        if operation is None:
            return None
        return _mutation_response(
            self._fresh(operation.deployment_id),
            operation,
            status.HTTP_200_OK,
            replay=True,
        )

    def _replay_operation(self, request: Request, request_hash: str) -> Response | None:
        operation, error = _idempotency_replay(request, request_hash)
        if error is not None:
            return error
        if operation is None:
            return None
        response = Response(RuntimeOperationSerializer(operation).data)
        response["Idempotent-Replay"] = "true"
        response["Cache-Control"] = "private, no-store"
        return response

    def _locked_deployment(self, deployment_id) -> RuntimeDeployment:
        return (
            RuntimeDeployment.objects.select_for_update()
            .select_related(
                "application",
                "release__application_version",
                "environment",
            )
            .get(pk=deployment_id)
        )

    def _fresh(self, deployment_id) -> RuntimeDeployment:
        return self.get_queryset().get(pk=deployment_id)

    @staticmethod
    def _create_components(deployment: RuntimeDeployment) -> None:
        modules_by_id = {
            module.id: module for module in deployment.application.modules.all()
        }
        components = []
        for manifest_component in deployment.release.manifest["modules"]:
            module = modules_by_id[manifest_component["module_id"]]
            policy = deployment.scaling[module.slug]
            desired = (
                policy["replicas"]
                if policy["mode"] == "fixed"
                else policy["min_replicas"]
            )
            components.append(
                RuntimeComponent(
                    deployment=deployment,
                    module=module,
                    image_digest=manifest_component["image"],
                    desired_replicas=desired,
                )
            )
        RuntimeComponent.objects.bulk_create(components)

    @staticmethod
    def _sync_component_scaling(deployment: RuntimeDeployment) -> None:
        for component in deployment.components.select_related("module"):
            policy = deployment.scaling[component.module.slug]
            component.desired_replicas = (
                policy["replicas"]
                if policy["mode"] == "fixed"
                else policy["min_replicas"]
            )
            component.save(update_fields=["desired_replicas", "updated_at"])


def _create_operation(
    request: Request,
    deployment: RuntimeDeployment,
    operation_type: str,
    request_hash: str,
    *,
    payload: dict[str, Any],
) -> RuntimeOperation:
    key = _idempotency_key(request)
    assert key is not None
    actor, actor_label = _actor(request)
    operation_payload = dict(payload)
    if operation_type != RuntimeOperation.OperationType.LOG_SNAPSHOT:
        operation_payload["desired_state"] = deployment.desired_state
    return RuntimeOperation.objects.create(
        deployment=deployment,
        operation_type=operation_type,
        payload=operation_payload,
        idempotency_key=key,
        request_hash=request_hash,
        target_generation=deployment.generation,
        actor=actor,
        actor_label=actor_label,
    )


def _idempotency_replay(
    request: Request,
    request_hash: str,
) -> tuple[RuntimeOperation | None, Response | None]:
    key = _idempotency_key(request)
    if key is None:
        return None, _problem(
            "Idempotency-Key is required for runtime mutations.",
            code="idempotency_key_required",
            status_code=428,
        )
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        return None, _problem(
            "Idempotency-Key must contain 8-128 safe characters.",
            code="invalid_idempotency_key",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    operation = RuntimeOperation.objects.filter(idempotency_key=key).first()
    if operation is None:
        return None, None
    if operation.request_hash != request_hash:
        return None, _problem(
            "The idempotency key was already used for a different request.",
            code="idempotency_conflict",
            status_code=status.HTTP_409_CONFLICT,
        )
    return operation, None


def _idempotency_key(request: Request) -> str | None:
    value = request.headers.get("Idempotency-Key")
    return value.strip() if value else None


def _application_precondition(
    request: Request,
    application: HostedApplication,
) -> Response | None:
    return _revision_precondition(
        request,
        application.revision,
        resource="application",
    )


def _deployment_precondition(
    request: Request,
    deployment: RuntimeDeployment,
) -> Response | None:
    return _revision_precondition(
        request,
        deployment.revision,
        resource="deployment",
    )


def _revision_precondition(
    request: Request,
    revision: int,
    *,
    resource: str,
) -> Response | None:
    value = request.headers.get("If-Match")
    if value is None:
        return _problem(
            f"If-Match is required for runtime {resource} mutations.",
            code="precondition_required",
            status_code=428,
        )
    match = re.fullmatch(r'"([1-9][0-9]*)"', value.strip())
    if match is None:
        return _problem(
            'If-Match must contain a strong revision ETag such as "3".',
            code="invalid_precondition",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if int(match.group(1)) != revision:
        response = _problem(
            f"The runtime {resource} changed after it was loaded.",
            code="stale_revision",
            status_code=status.HTTP_412_PRECONDITION_FAILED,
        )
        response["ETag"] = _etag(revision)
        return response
    return None


def _busy_response(deployment: RuntimeDeployment) -> Response | None:
    if deployment.operations.filter(
        status__in=[RuntimeOperation.Status.QUEUED, RuntimeOperation.Status.RUNNING]
    ).exists():
        return _problem(
            "Another runtime operation is already in progress.",
            code="operation_in_progress",
            status_code=status.HTTP_409_CONFLICT,
        )
    return None


def _validate_transition(
    deployment: RuntimeDeployment,
    action_name: str,
) -> Response | None:
    if deployment.deleted_at is not None:
        return _problem(
            "A deleted deployment cannot accept runtime actions.",
            code="deployment_deleted",
            status_code=status.HTTP_409_CONFLICT,
        )
    state = deployment.observed_state
    allowed = {
        "start": {"stopped", "failed", "unknown"},
        "stop": {"running", "degraded", "failed", "unknown"},
        "restart": {"running", "degraded"},
        "scale": {"running", "degraded", "stopped"},
    }
    if state not in allowed[action_name]:
        return _problem(
            f"Action {action_name} is not valid while the deployment is {state}.",
            code="invalid_runtime_transition",
            status_code=status.HTTP_409_CONFLICT,
        )
    return None


def _actor(request: Request):
    user = request.user
    label = str(getattr(user, "acl_username", getattr(user, "username", user)))[:255]
    user_id = getattr(user, "pk", None)
    if user_id is None:
        return None, label
    actor = get_user_model().objects.filter(pk=user_id).first()
    return actor, label


def _runtime_unavailable() -> Response | None:
    if settings.RUNTIME_ENABLED:
        return None
    return _problem(
        "Runtime operations require an isolated controller configuration.",
        code="runtime_backend_unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _request_hash(scope: str, payload: object) -> str:
    canonical = json.dumps(
        {"scope": scope, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _mutation_response(
    deployment: RuntimeDeployment,
    operation: RuntimeOperation,
    status_code: int,
    *,
    replay: bool = False,
) -> Response:
    response = Response(
        {
            "deployment": RuntimeDeploymentSerializer(deployment).data,
            "operation": RuntimeOperationSerializer(operation).data,
        },
        status=status_code,
    )
    response["ETag"] = _etag(deployment.revision)
    response["Cache-Control"] = "private, no-store"
    if replay:
        response["Idempotent-Replay"] = "true"
    return response


def _problem(detail: str, *, code: str, status_code: int) -> Response:
    return Response({"detail": detail, "code": code}, status=status_code)


def _etag(revision: int) -> str:
    return f'"{revision}"'
