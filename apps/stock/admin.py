from django.contrib import admin

from apps.stock.models import Stock, StockMovement

admin.site.register(Stock)
admin.site.register(StockMovement)
