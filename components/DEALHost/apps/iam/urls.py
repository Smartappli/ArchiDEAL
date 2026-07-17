from rest_framework.routers import DefaultRouter

from .views import GroupViewSet, PermissionViewSet, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="iam-users")
router.register("groups", GroupViewSet, basename="iam-groups")
router.register("permissions", PermissionViewSet, basename="iam-permissions")

urlpatterns = [
    *router.urls,
]
