from django.db.models import Sum

from apps.sales.models import Sale
from config.money import to_money


def update_sale_payment_status(sale):
    paid_amount = to_money(sale.payments.aggregate(total=Sum("amount"))["total"])
    sale_total = to_money(sale.total)

    if paid_amount >= sale_total:
        sale.payment_status = Sale.PaymentStatus.PAID

    elif paid_amount > 0:
        sale.payment_status = Sale.PaymentStatus.PARTIAL

    else:
        sale.payment_status = Sale.PaymentStatus.UNPAID

    sale.save(update_fields=["payment_status"])

    return paid_amount