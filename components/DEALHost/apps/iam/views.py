from django.http import Http404
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group, Permission
from django.views.generic import TemplateView
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.events import publish_event
from apps.common.events.subjects import IAM_OIDC_ACL_IDENTITY_DEPROVISIONED
from apps.common.permissions import IsSuperUser

from .models import OIDCAclIdentity

from .serializers import (
    GroupSerializer,
    OIDCAclIdentityProvisionSerializer,
    OIDCAclIdentitySerializer,
    PasswordChangeSerializer,
    PermissionSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from .services import (
    OIDCAclIdentityConflict,
    deprovision_oidc_acl_identity,
    provision_oidc_acl_identity,
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
        User.objects.select_related("oidc_acl_identity")
        .prefetch_related("groups", "user_permissions")
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

    @staticmethod
    def _is_oidc_acl_user(user) -> bool:
        return OIDCAclIdentity.objects.filter(user=user).exists()

    def update(self, request: Request, *args, **kwargs) -> Response:
        user = self.get_object()
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            user,
            data=request.data,
            partial=partial,
        )
        is_oidc_acl_user = self._is_oidc_acl_user(user)
        if is_oidc_acl_user:
            # The stable username deliberately contains the ``oidc:`` prefix,
            # which Django's interactive username validator does not accept.
            # This endpoint compares it below and never permits a different
            # value, so re-submitting an unchanged PUT/PATCH stays compatible.
            serializer.fields["username"].validators = []
        serializer.is_valid(raise_exception=True)
        protected_fields = [
            field_name
            for field_name in ("username", "is_staff", "is_superuser")
            if field_name in serializer.validated_data
            and serializer.validated_data[field_name] != getattr(user, field_name)
        ]
        if is_oidc_acl_user and protected_fields:
            return Response(
                {
                    "detail": (
                        "Stable OIDC ACL users cannot change their username or "
                        "privilege flags through the User API."
                    ),
                    "protected_fields": protected_fields,
                },
                status=status.HTTP_409_CONFLICT,
            )
        self.perform_update(serializer)
        if getattr(user, "_prefetched_objects_cache", None):
            user._prefetched_objects_cache = {}
        return Response(serializer.data)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        user = self.get_object()
        if self._is_oidc_acl_user(user):
            return Response(
                {
                    "detail": (
                        "This technical user is protected by an OIDC ACL identity "
                        "and cannot be deleted through the User API."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request: Request, pk: str | None = None) -> Response:
        user = self.get_object()
        if self._is_oidc_acl_user(user):
            return Response(
                {
                    "detail": (
                        "Stable OIDC ACL users must remain without a usable password."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"user": user},
        )
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class OIDCAclIdentityViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Provision opaque local ACL users from stable OIDC issuer/subject pairs."""

    queryset = OIDCAclIdentity.objects.select_related("user").all()
    serializer_class = OIDCAclIdentitySerializer
    permission_classes = [IsSuperUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "issuer",
        "subject",
        "display_name",
        "email",
        "user__username",
    ]
    ordering_fields = ["issuer", "subject", "display_name", "created_at", "updated_at"]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def list(self, request: Request, *args, **kwargs) -> Response:
        response = super().list(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        if request.data:
            return Response(
                {
                    "detail": "DELETE does not accept a request body.",
                    "code": "delete_body_not_allowed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        identity_id = self.get_object().pk
        try:
            result = deprovision_oidc_acl_identity(identity_id=identity_id)
        except OIDCAclIdentity.DoesNotExist as exc:
            # The row can disappear between the initial permission-aware lookup
            # and the transactional lock in a concurrent request.
            raise Http404 from exc
        except OIDCAclIdentityConflict as exc:
            return Response(
                {"detail": str(exc), "code": "oidc_identity_conflict"},
                status=status.HTTP_409_CONFLICT,
            )

        actor = str(
            getattr(
                request.user,
                "acl_username",
                getattr(request.user, "username", "unknown"),
            )
        )
        publish_event(
            event_type=IAM_OIDC_ACL_IDENTITY_DEPROVISIONED,
            data={
                "identity_id": result.identity_id,
                "user_id": result.user_id,
                "acl_username": result.acl_username,
                "actor": actor,
            },
            producer="apps.iam.OIDCAclIdentityViewSet",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = OIDCAclIdentityProvisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = provision_oidc_acl_identity(**serializer.validated_data)
        except OIDCAclIdentityConflict as exc:
            return Response(
                {"detail": str(exc), "code": "oidc_identity_conflict"},
                status=status.HTTP_409_CONFLICT,
            )

        data = dict(OIDCAclIdentitySerializer(result.identity).data)
        data["created"] = result.created
        data["metadata_updated"] = result.metadata_updated
        response = Response(
            data,
            status=(status.HTTP_201_CREATED if result.created else status.HTTP_200_OK),
        )
        response["Cache-Control"] = "no-store"
        return response


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
