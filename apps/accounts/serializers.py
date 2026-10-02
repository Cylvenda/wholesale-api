from rest_framework.fields import DateField
from rest_framework import serializers
import re
from djoser.serializers import (
    UserCreateSerializer as BaseUserCreateSerializer,
    UserSerializer as BaseUserSerializer,
)

from .models import User


def sync_staff_flags(user) -> None:
    """Keep ``is_staff`` aligned with the role the API actually accepts.

    The user form can set ``role="admin"``, but the flag that ``IsAdminUser``
    and the Django admin check is ``is_staff``. Without this, a promoted admin
    is refused by the very endpoints their role grants.
    """
    should_be_staff = user.role == User.Roles.ADMIN
    if bool(user.is_staff) != should_be_staff:
        user.is_staff = should_be_staff
        user.save(update_fields=["is_staff"])


class UserCreateSerializer(BaseUserCreateSerializer):

    def validate(self, attrs):
        attrs = super().validate(attrs)
        password = attrs["password"]
        errors = []

        if len(password) > 20:
            errors.append("Password must be no longer than 20 characters.")
        if not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter.")
        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter.")
        if not re.search(r"[0-9]", password):
            errors.append("Password must contain at least one number.")
        if not re.search(r"[^a-zA-Z0-9]", password):
            errors.append("Password must contain at least one special character.")

        if errors:
            raise serializers.ValidationError({"password": errors})
        return attrs

    def create(self, validated_data):
        user = super().create(validated_data)
        sync_staff_flags(user)
        return user

    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = [
            "uuid",
            "email",
            "phone",
            "first_name",
            "last_name",
            "password",
            "role",
            "is_active",
        ]
        read_only_fields = ["uuid"]


class UserSerializer(BaseUserSerializer):

    def update(self, instance, validated_data):
        user = super().update(instance, validated_data)
        sync_staff_flags(user)
        return user

    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = [
            "uuid",
            "email",
            "phone",
            "first_name",
            "last_name",
            "username",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
        ]
        read_only_fields = [
            "uuid",
            "email",
            "phone",
            "username",
            "is_staff",
            "is_superuser",
            "date_joined",
        ]
