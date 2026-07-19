"""
URL configuration for core project.

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
from core_data.views import (
    ExperimentDetailView,
    ExperimentListCreateView,
    health_live,
    health_ready,
    metrics,
)

urlpatterns = [
    path(
        "api/experiments/",
        ExperimentListCreateView.as_view(),
        name="experiment-list",
    ),
    path(
        "api/experiments/<uuid:experiment_id>/",
        ExperimentDetailView.as_view(),
        name="experiment-detail",
    ),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("metrics/", metrics, name="metrics"),
    path("admin/", admin.site.urls),
]
