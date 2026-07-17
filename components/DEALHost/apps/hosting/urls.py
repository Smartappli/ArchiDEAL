from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AutoDiscoverView,
    HostedApplicationViewSet,
    ModuleViewSet,
    ToolViewSet,
)

router = DefaultRouter()
router.register("modules", ModuleViewSet, basename="modules")
router.register("tools", ToolViewSet, basename="tools")
router.register("applications", HostedApplicationViewSet, basename="applications")

urlpatterns = [
    *router.urls,
    path("autodiscover/", AutoDiscoverView.as_view(), name="hosting-autodiscover"),
]
