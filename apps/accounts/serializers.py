from rest_framework.fields import DateField
from rest_framework import serializers
from djoser.serializers import (
    UserCreateSerializer as BaseUserCreateSerializer,
    UserSerializer as BaseUserSerializer,
)

from .models import User


class UserCreateSerializer(BaseUserCreateSerializer):

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
            "date_joined"
        ]
        read_only_fields = [
            "uuid",
            "email",
            "phone",
            "username",
            "is_staff",
            "is_superuser",
            "date_joined"
        ]
