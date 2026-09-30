from rest_framework.fields import DateField
from rest_framework import serializers
import re
from djoser.serializers import (
    UserCreateSerializer as BaseUserCreateSerializer,
    UserSerializer as BaseUserSerializer,
)

from .models import User


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
