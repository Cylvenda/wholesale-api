from django.db import models
from config.models import BaseModel


class ExpenseCategory(BaseModel):
    name = models.CharField(
        max_length=100,
        unique=True
    )

    def __str__(self):
        return self.name

class Expense(BaseModel):
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    expense_date = models.DateTimeField()

    def __str__(self):
        return f"{self.category.name} - {self.amount}"
