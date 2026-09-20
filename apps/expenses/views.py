from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from .models import Expense, ExpenseCategory
from .serializers import ExpenseSerializer, ExpenseCategorySerializer


class ExpenseCategoryViewSet(ModelViewSet):
    queryset = ExpenseCategory.objects.all().order_by("-created_at")
    serializer_class = ExpenseCategorySerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class ExpenseViewSet(ModelViewSet):
    queryset = Expense.objects.select_related("category").prefetch_related().order_by("-created_at")
    serializer_class = ExpenseSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()
