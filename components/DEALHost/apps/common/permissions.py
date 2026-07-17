from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaffOrAuthenticatedReadOnly(BasePermission):
    """Allow authenticated reads and restrict writes to staff users."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_staff)


class IsSuperUser(BasePermission):
    """Restrict access to Django superusers or equivalent admin API tokens."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
