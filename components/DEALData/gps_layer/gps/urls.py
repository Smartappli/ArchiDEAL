"""
URL configuration for research_layer project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

"""

# pylint: disable=no-name-in-module

from django.contrib import admin
from django.urls import path
from gps_data.views import (
    GPSSensorDetailView,
    GPSSensorListCreateView,
    WildFiGPSBatchIngestView,
    WildFiGPSIngestView,
    WildFiGPSListView,
    health_live,
    health_ready,
    metrics,
)

urlpatterns = [
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("metrics/", metrics, name="metrics"),
    path(
        "api/gps-sensors/",
        GPSSensorListCreateView.as_view(),
        name="gps-sensor-list",
    ),
    path(
        "api/gps-sensors/<uuid:pk>/",
        GPSSensorDetailView.as_view(),
        name="gps-sensor-detail",
    ),
    path("api/wildfi/gps/", WildFiGPSListView.as_view(), name="wildfi-gps-list"),
    path(
        "api/ingest/wildfi/gps/",
        WildFiGPSIngestView.as_view(),
        name="wildfi-gps-ingest",
    ),
    path(
        "api/ingest/wildfi/gps/batch/",
        WildFiGPSBatchIngestView.as_view(),
        name="wildfi-gps-batch-ingest",
    ),
    path("admin/", admin.site.urls),
]
