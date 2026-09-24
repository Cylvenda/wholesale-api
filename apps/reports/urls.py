from django.urls import path

from .views import export_purchases_excel, export_sales_excel, sale_receipt

urlpatterns = [
    path("reports/purchases/export/", export_purchases_excel, name="purchases-export"),
    path("reports/sales/export/", export_sales_excel, name="sales-export"),
    path("sales/<uuid:uuid>/receipt/", sale_receipt, name="sale-receipt"),
]
