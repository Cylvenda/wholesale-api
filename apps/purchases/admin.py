from django.contrib import admin

from apps.purchases.models import Purchase, PurchaseItem

admin.site.register(Purchase)
admin.site.register(PurchaseItem)
