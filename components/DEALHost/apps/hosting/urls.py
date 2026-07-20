from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AutoDiscoverView,
    DatasetPrincipalListView,
    DatasetViewSet,
    HostedApplicationViewSet,
    ModuleViewSet,
    ToolViewSet,
)
from .runtime_views import (
    RuntimeDeploymentViewSet,
    RuntimeEnvironmentViewSet,
    RuntimeOperationViewSet,
)

router = DefaultRouter()
router.register("modules", ModuleViewSet, basename="modules")
router.register("tools", ToolViewSet, basename="tools")
router.register("applications", HostedApplicationViewSet, basename="applications")
router.register("deployments", RuntimeDeploymentViewSet, basename="deployments")
router.register(
    "runtime-environments",
    RuntimeEnvironmentViewSet,
    basename="runtime-environments",
)
router.register("operations", RuntimeOperationViewSet, basename="operations")
router.register("datasets", DatasetViewSet, basename="datasets")

urlpatterns = [
    *router.urls,
    path(
        "dataset-principals/",
        DatasetPrincipalListView.as_view(),
        name="dataset-principals",
    ),
    path("autodiscover/", AutoDiscoverView.as_view(), name="hosting-autodiscover"),
]
