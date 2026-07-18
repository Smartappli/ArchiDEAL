import hashlib
import uuid

from django.core.cache import cache, caches
from django.db import connections
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.events import publish_event
from apps.common.events.subjects import (
    GATEWAY_GITHUB_WEBHOOK_RECEIVED,
    GATEWAY_ROUTE_PUBLISH_COMPLETED,
    GATEWAY_ROUTE_PUBLISH_FAILED,
    GATEWAY_ROUTE_PUBLISH_REQUESTED,
)

from .services import ApisixService, GitHubService, normalize_module_slug

GITHUB_WEBHOOK_DELIVERY_TTL = 24 * 60 * 60


def _is_truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _github_delivery_cache_key(delivery_id: str) -> str:
    digest = hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()
    return f"gateway:github-webhook:{digest}"


def _database_is_ready() -> bool:
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
    return bool(row and row[0] == 1)


def _cache_is_ready() -> bool:
    readiness_cache = caches["default"]
    token = uuid.uuid4().hex
    key = f"gateway:health:{token}"
    readiness_cache.set(key, token, timeout=5)
    return readiness_cache.get(key) == token


class LiveHealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "gateway"})


class ReadyHealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        dependencies = {}
        for name, check in (
            ("database", _database_is_ready),
            ("cache", _cache_is_ready),
        ):
            try:
                available = check()
            except Exception:  # Dependency clients expose heterogeneous failures.
                available = False
            dependencies[name] = "available" if available else "unavailable"

        ready = all(value == "available" for value in dependencies.values())
        return Response(
            {
                "status": "ok" if ready else "unavailable",
                "service": "gateway",
                **dependencies,
            },
            status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class HealthView(ReadyHealthView):
    """Backward-compatible readiness endpoint used by existing integrations."""


class SyncGitHubView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        branch = request.data.get("branch", "main")
        if not isinstance(branch, str) or not branch.strip():
            return Response(
                {"detail": _("branch must be a non-empty string.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        branch = branch.strip()
        repository = request.data.get("repository_full_name")
        repository_payload = request.data.get("repository")
        if not repository and isinstance(repository_payload, dict):
            repository = repository_payload.get("full_name")
        elif not repository:
            repository = repository_payload
        github = GitHubService()
        if repository and not github.is_allowed_repository_full_name(str(repository)):
            return Response(
                {
                    "detail": _("Repository is not allowed."),
                    "repository": repository,
                    "allowed_repositories": github.allowed_repository_full_names(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        commit = github.latest_commit(
            branch=branch,
            repository_full_name=str(repository) if repository else None,
        )
        return Response(
            {
                "repository": f"{commit['repository']['full_name']}",
                "branch": branch,
                "sha": commit["sha"],
                "message": commit["commit"]["message"],
            },
        )


class GitHubRepositoriesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"repositories": GitHubService().repository_integrations()},
            status=status.HTTP_200_OK,
        )


class PublishRouteView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        module_slug = request.data.get("module_slug")
        dry_run = _is_truthy(request.data.get("dry_run", False))
        if not module_slug or not str(module_slug).strip():
            return Response(
                {"detail": _("module_slug is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            module_slug = normalize_module_slug(module_slug)
        except ValueError:
            return Response(
                {
                    "detail": _(
                        "module_slug must contain only letters, numbers, "
                        "hyphens or underscores.",
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        publish_event(
            event_type=GATEWAY_ROUTE_PUBLISH_REQUESTED,
            data={"module_slug": module_slug, "dry_run": dry_run},
            producer="apps.gateway.PublishRouteView",
        )
        try:
            result = ApisixService().publish_route(module_slug, dry_run=dry_run)
        except Exception as exc:
            publish_event(
                event_type=GATEWAY_ROUTE_PUBLISH_FAILED,
                data={"module_slug": module_slug, "error": str(exc)},
                producer="apps.gateway.PublishRouteView",
            )
            raise
        publish_event(
            event_type=GATEWAY_ROUTE_PUBLISH_COMPLETED,
            data={
                "module_slug": module_slug,
                "route_id": result.get("route_id"),
                "dry_run": result.get("dry_run", dry_run),
            },
            producer="apps.gateway.PublishRouteView",
        )
        return Response(result, status=status.HTTP_201_CREATED)


class GitHubWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_payload = request.body
        signature = request.headers.get("X-Hub-Signature-256")
        github = GitHubService()

        if not github.verify_signature(raw_payload, signature):
            return Response(
                {"detail": _("Invalid GitHub signature.")},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        delivery_id = request.headers.get("X-GitHub-Delivery", "").strip()
        if not delivery_id:
            return Response(
                {"detail": _("Missing GitHub delivery id.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repository = github.repository_full_name(payload)
        event = request.headers.get("X-GitHub-Event", "").strip()
        if not event:
            return Response(
                {"detail": _("Missing GitHub event.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expected_repository = github.expected_repository_full_name()
        allowed_repositories = github.allowed_repository_full_names()
        if not github.is_expected_repository(payload):
            return Response(
                {
                    "ignored": True,
                    "detail": _(
                        "Webhook repository does not match configured repository.",
                    ),
                    "repository": repository,
                    "expected_repository": expected_repository,
                    "allowed_repositories": allowed_repositories,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        if not github.is_allowed_event(repository, event):
            return Response(
                {
                    "ignored": True,
                    "detail": _("Webhook event is not allowed for repository."),
                    "event": event,
                    "repository": repository,
                    "allowed_events": github.allowed_events_for_repository(repository),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        cache_key = _github_delivery_cache_key(delivery_id)
        if not cache.add(cache_key, True, timeout=GITHUB_WEBHOOK_DELIVERY_TTL):
            return Response(
                {
                    "ignored": True,
                    "detail": _("GitHub webhook delivery was already processed."),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            return self._process_webhook(
                github=github,
                payload=payload,
                event=event,
                repository=repository,
            )
        except Exception:
            cache.delete(cache_key)
            raise

    def _process_webhook(self, *, github, payload, event: str, repository: str):
        module_slugs = github.module_slugs_for_webhook(payload)
        publish_event(
            event_type=GATEWAY_GITHUB_WEBHOOK_RECEIVED,
            data={
                "event": event,
                "repository": repository,
                "module_slugs": module_slugs,
            },
            producer="apps.gateway.GitHubWebhookView",
        )

        routes = []
        for module_slug in module_slugs:
            publish_event(
                event_type=GATEWAY_ROUTE_PUBLISH_REQUESTED,
                data={"module_slug": module_slug, "source": "github_webhook"},
                producer="apps.gateway.GitHubWebhookView",
            )
            try:
                route_status = ApisixService().publish_route(
                    module_slug,
                    dry_run=False,
                )
            except Exception as exc:
                publish_event(
                    event_type=GATEWAY_ROUTE_PUBLISH_FAILED,
                    data={"module_slug": module_slug, "error": str(exc)},
                    producer="apps.gateway.GitHubWebhookView",
                )
                raise
            publish_event(
                event_type=GATEWAY_ROUTE_PUBLISH_COMPLETED,
                data={
                    "module_slug": module_slug,
                    "route_id": route_status.get("route_id"),
                    "skipped": route_status.get("skipped", False),
                },
                producer="apps.gateway.GitHubWebhookView",
            )
            routes.append(
                {
                    "module_slug": module_slug,
                    "route": route_status["route_id"],
                    "skipped": route_status.get("skipped", False),
                },
            )

        return Response(
            {
                "event": event,
                "repository": repository,
                "module_slugs": module_slugs,
                "routes": routes,
            },
            status=status.HTTP_202_ACCEPTED,
        )
