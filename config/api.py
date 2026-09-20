from datetime import timedelta

import csv
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.products.models import Product
from apps.purchases.models import Purchase
from apps.sales.models import Sale
from apps.stock.models import Stock
from apps.payments.models import Payment


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    total_products = Product.objects.count()
    stock_units = Stock.objects.aggregate(total=Sum("quantity"))["total"] or 0

    sales_value = Sale.objects.filter(
        status=Sale.Status.COMPLETED
    ).aggregate(total=Sum("total"))["total"] or 0

    draft_purchases = Purchase.objects.filter(
        status=Purchase.Status.DRAFT
    ).count()

    purchases_value = Purchase.objects.filter(
        status=Purchase.Status.COMPLETED
    ).aggregate(total=Sum("total"))["total"] or 0

    low_stock_items = Stock.objects.filter(quantity__gt=0, quantity__lt=10).count()
    out_of_stock_items = Stock.objects.filter(quantity=0).count()

    recent_sales = Sale.objects.filter(
        status=Sale.Status.COMPLETED
    ).select_related("customer").order_by("-sale_date")[:5]

    sales_by_day = (
        Sale.objects.filter(
            status=Sale.Status.COMPLETED,
            sale_date__gte=week_ago,
        )
        .extra({"day": "date(sale_date)"})
        .values("day")
        .annotate(amount=Sum("total"))
        .order_by("day")
    )

    purchases_by_day = (
        Purchase.objects.filter(
            status=Purchase.Status.COMPLETED,
            purchase_date__gte=week_ago,
        )
        .extra({"day": "date(purchase_date)"})
        .values("day")
        .annotate(amount=Sum("total"))
        .order_by("day")
    )

    sales_map = {}
    for entry in sales_by_day:
        day_key = entry["day"]
        if hasattr(day_key, "isoformat"):
            day_key = day_key.isoformat()
        sales_map[str(day_key)] = float(entry["amount"] or 0)

    purchases_map = {}
    for entry in purchases_by_day:
        day_key = entry["day"]
        if hasattr(day_key, "isoformat"):
            day_key = day_key.isoformat()
        purchases_map[str(day_key)] = float(entry["amount"] or 0)

    chart_data = []
    current = week_ago
    while current <= now:
        day_str = current.date().isoformat()
        chart_data.append({
            "day": current.strftime("%a"),
            "date": day_str,
            "amount": sales_map.get(day_str, 0),
            "purchases": purchases_map.get(day_str, 0),
        })
        current += timedelta(days=1)

    return Response({
        "total_products": total_products,
        "stock_units": stock_units,
        "sales_value": sales_value,
        "purchases_value": purchases_value,
        "draft_purchases": draft_purchases,
        "low_stock_items": low_stock_items,
        "out_of_stock_items": out_of_stock_items,
        "recent_sales": [
            {
                "uuid": str(sale.uuid),
                "customer_name": sale.customer.name if sale.customer else None,
                "sale_date": sale.sale_date.isoformat() if sale.sale_date else None,
                "total": str(sale.total),
                "payment_status": sale.payment_status,
            }
            for sale in recent_sales
        ],
        "chart_data": chart_data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_report(request):
    """
    Export a report as CSV.
    Accepts ?type=sales|purchases|stock|movements|payments
    """
    report_type = request.query_params.get("type", "sales")

    if report_type == "sales":
        rows = Sale.objects.select_related("customer").prefetch_related("items")
        filename = "sales-report"
        headers = [
            "UUID", "Customer", "Date", "Status", "Payment status",
            "Subtotal", "Discount", "Total", "Notes",
        ]
        data = [
            [
                str(sale.uuid),
                sale.customer.name if sale.customer else "",
                sale.sale_date.isoformat() if sale.sale_date else "",
                sale.status, sale.payment_status,
                str(sale.subtotal), str(sale.discount), str(sale.total),
                sale.notes,
            ]
            for sale in rows
        ]
    elif report_type == "purchases":
        rows = Purchase.objects.select_related("supplier").prefetch_related("items")
        filename = "purchases-report"
        headers = [
            "UUID", "Supplier", "Invoice", "Date", "Status",
            "Total", "Notes",
        ]
        data = [
            [
                str(p.uuid),
                p.supplier.name if p.supplier else "",
                p.invoice_number,
                p.purchase_date.isoformat() if p.purchase_date else "",
                p.status, str(p.total), p.notes,
            ]
            for p in rows
        ]
    elif report_type == "stock":
        rows = Stock.objects.select_related("product")
        filename = "stock-report"
        headers = ["UUID", "Product", "SKU", "Quantity", "Buying price", "Selling price"]
        data = [
            [
                str(s.uuid), s.product.name, s.product.uuid,
                s.quantity, str(s.product.buying_price), str(s.product.selling_price),
            ]
            for s in rows
        ]
    elif report_type == "movements":
        rows = Stock.objects.select_related("product")
        # We need the movements directly
        from apps.stock.models import StockMovement
        movements = StockMovement.objects.select_related("stock", "stock__product")
        filename = "stock-movements-report"
        headers = [
            "UUID", "Product", "Movement type", "Quantity",
            "Reference", "Notes", "Created at",
        ]
        data = [
            [
                str(m.uuid),
                m.stock.product.name if m.stock else "",
                m.movement_type, str(m.quantity),
                m.reference, m.notes,
                m.created_at.isoformat() if m.created_at else "",
            ]
            for m in movements
        ]
    elif report_type == "payments":
        rows = Payment.objects.select_related("customer", "sale")
        filename = "payments-report"
        headers = [
            "UUID", "Customer", "Sale", "Amount", "Method",
            "Reference", "Date", "Notes",
        ]
        data = [
            [
                str(p.uuid),
                p.customer.name if p.customer else "",
                str(p.sale.uuid) if p.sale else "",
                str(p.amount), p.method, p.reference,
                p.payment_date.isoformat() if p.payment_date else "",
                p.notes,
            ]
            for p in rows
        ]
    else:
        return Response(
            {"detail": f"Unknown report type: {report_type}"},
            status=400,
        )

    date_str = timezone.now().strftime("%Y-%m-%d")
    filename = f"{filename}-{date_str}"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(headers)
    for row in data:
        writer.writerow(row)

    return response
