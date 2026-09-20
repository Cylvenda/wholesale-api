from django.db import transaction
from rest_framework import serializers

class BaseSerializer(serializers.ModelSerializer):

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user

        return super().create(validated_data)

    class Meta:
        read_only_fields = [
            "id",
            "uuid",
            "created_by",
            "created_at",
            "updated_at",
        ]