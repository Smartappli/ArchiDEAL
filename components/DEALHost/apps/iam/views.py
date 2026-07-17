from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group, Permission
from django.views.generic import TemplateView
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.permissions import IsSuperUser

from .serializers import (
    GroupSerializer,
    PasswordChangeSerializer,
    PermissionSerializer,
    UserCreateSerializer,
    UserSerializer,
)

User = get_user_model()


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Permission.objects.select_related("content_type")
        .all()
        .order_by("content_type__app_label", "codename")
    )
    serializer_class = PermissionSerializer
    permission_classes = [IsSuperUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "name",
        "codename",
        "content_type__app_label",
        "content_type__model",
    ]
    ordering_fields = ["name", "codename", "content_type__app_label"]


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.prefetch_related("permissions").all().order_by("name")
    serializer_class = GroupSerializer
    permission_classes = [IsSuperUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "permissions__codename"]
    ordering_fields = ["name"]


class UserViewSet(viewsets.ModelViewSet):
    queryset = (
        User.objects.prefetch_related("groups", "user_permissions")
        .all()
        .order_by("username")
    )
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    permission_classes = [IsSuperUser]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["username", "email", "date_joined", "last_login"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request: Request, pk: str | None = None) -> Response:
        user = self.get_object()
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"user": user},
        )
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuperUserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self) -> bool:
        return bool(self.request.user.is_superuser)


class IamManagementInterfaceView(SuperUserRequiredMixin, TemplateView):
    template_name = "iam/manage.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["users"] = (
            User.objects.prefetch_related("groups").all().order_by("username")
        )
        context["groups"] = (
            Group.objects.prefetch_related("permissions").all().order_by("name")
        )
        context["permissions"] = (
            Permission.objects.select_related("content_type")
            .all()
            .order_by("content_type__app_label", "codename")
        )
        return context
