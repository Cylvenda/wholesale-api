from django.contrib import admin

from apps.expenses.models import ExpenseCategory, Expense

admin.site.register(ExpenseCategory)
admin.site.register(Expense)
