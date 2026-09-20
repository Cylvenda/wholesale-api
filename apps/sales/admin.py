from django.contrib import admin

from apps.sales.models import Sale, SaleItem

admin.site.register(Sale)
admin.site.register(SaleItem)
