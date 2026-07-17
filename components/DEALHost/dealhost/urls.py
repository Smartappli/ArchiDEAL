from django.contrib import admin
from django.urls import include, path

from apps.hosting.views import ManagementAutoDiscoverView, ManagementInterfaceView
from apps.iam.views import IamManagementInterfaceView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/hosting/", include("apps.hosting.urls")),
    path("api/iam/", include("apps.iam.urls")),
    path("api/gateway/", include("apps.gateway.urls")),
    path(
        "hosting/manage/",
        ManagementInterfaceView.as_view(),
        name="hosting-management",
    ),
    path("iam/manage/", IamManagementInterfaceView.as_view(), name="iam-management"),
    path(
        "hosting/manage/autodiscover/",
        ManagementAutoDiscoverView.as_view(),
        name="hosting-management-autodiscover",
    ),
]
