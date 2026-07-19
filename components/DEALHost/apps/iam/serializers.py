from collections.abc import Mapping

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.common.oidc import (
    validate_approved_oidc_issuer,
    validate_oidc_subject,
)

from .models import OIDCAclIdentity

User = get_user_model()


class OIDCAclIdentitySummarySerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = OIDCAclIdentity
        fields = ["issuer", "subject", "display_name", "email", "label"]
        read_only_fields = fields

    def get_label(self, identity: OIDCAclIdentity) -> str:
        return identity.display_name or identity.email or identity.subject


class OIDCAclIdentitySerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    acl_username = serializers.CharField(source="user.username", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = OIDCAclIdentity
        fields = [
            "id",
            "user_id",
            "acl_username",
            "issuer",
            "subject",
            "display_name",
            "email",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OIDCAclIdentityProvisionSerializer(serializers.Serializer):
    issuer = serializers.CharField(max_length=512, trim_whitespace=False)
    subject = serializers.CharField(max_length=255, trim_whitespace=False)
    display_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    email = serializers.EmailField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - {"issuer", "subject", "display_name", "email"})
            if unknown:
                raise serializers.ValidationError(
                    {
                        "unknown_fields": [
                            f"Unsupported field: {name}" for name in unknown
                        ]
                    }
                )
        return super().to_internal_value(data)

    def validate_issuer(self, value: str) -> str:
        try:
            return validate_approved_oidc_issuer(
                value,
                str(getattr(settings, "DEALHOST_OIDC_ISSUER", "")),
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_subject(self, value: str) -> str:
        try:
            return validate_oidc_subject(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "content_type"]
        read_only_fields = fields


class GroupSerializer(serializers.ModelSerializer):
    permission_ids = serializers.PrimaryKeyRelatedField(
        source="permissions",
        queryset=Permission.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = Group
        fields = ["id", "name", "permissions", "permission_ids"]
        read_only_fields = ["id", "permissions"]


class UserSerializer(serializers.ModelSerializer):
    oidc_identity = OIDCAclIdentitySummarySerializer(
        source="oidc_acl_identity",
        read_only=True,
        allow_null=True,
    )
    group_ids = serializers.PrimaryKeyRelatedField(
        source="groups",
        queryset=Group.objects.all(),
        many=True,
        required=False,
    )
    permission_ids = serializers.PrimaryKeyRelatedField(
        source="user_permissions",
        queryset=Permission.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "group_ids",
            "user_permissions",
            "permission_ids",
            "date_joined",
            "last_login",
            "oidc_identity",
        ]
        read_only_fields = [
            "id",
            "groups",
            "user_permissions",
            "date_joined",
            "last_login",
            "oidc_identity",
        ]


class UserCreateSerializer(UserSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["password"]

    def validate(self, attrs):
        candidate = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        groups = validated_data.pop("groups", [])
        user_permissions = validated_data.pop("user_permissions", [])
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        if groups:
            user.groups.set(groups)
        if user_permissions:
            user.user_permissions.set(user_permissions)
        return user


class PasswordChangeSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value: str) -> str:
        validate_password(value, user=self.context.get("user"))
        return value
