from django.urls import path

from .views import (
    GitHubRepositoriesView,
    GitHubWebhookView,
    HealthView,
    LiveHealthView,
    PublishRouteView,
    ReadyHealthView,
    SyncGitHubView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="gateway-health"),
    path("health/live/", LiveHealthView.as_view(), name="gateway-health-live"),
    path("health/ready/", ReadyHealthView.as_view(), name="gateway-health-ready"),
    path("github/sync/", SyncGitHubView.as_view(), name="github-sync"),
    path(
        "github/repositories/",
        GitHubRepositoriesView.as_view(),
        name="github-repositories",
    ),
    path("github/webhook/", GitHubWebhookView.as_view(), name="github-webhook"),
    path("apisix/publish/", PublishRouteView.as_view(), name="apisix-publish"),
]
