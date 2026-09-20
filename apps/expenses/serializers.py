from rest_framework import serializers
from django.utils import timezone
from config.serializers import BaseSerializer
from .models import Expense, ExpenseCategory


class ExpenseCategorySerializer(BaseSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["uuid", "name", "created_at"]
        read_only_fields = ["uuid", "created_at"]


class ExpenseSerializer(BaseSerializer):
    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    category = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=ExpenseCategory.objects.all()
    )

    class Meta:
        model = Expense
        fields = [
            "uuid",
            "category",
            "category_name",
            "amount",
            "description",
            "expense_date",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["uuid", "category_name", "created_at", "created_by"]

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Expense amount cannot be negative."
            )
        return value

    def validate_expense_date(self, value):

        if value > timezone.now():
            raise serializers.ValidationError(
                "Expense date cannot be in the future."
            )
        return value
