from django.db.models import Sum
from apps.sales.models import Sale


def update_sale_payment_status(sale):
    paid_amount = (
        sale.payments.aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    if paid_amount >= sale.total:
        sale.payment_status = Sale.PaymentStatus.PAID

    elif paid_amount > 0:
        sale.payment_status = Sale.PaymentStatus.PARTIAL

    else:
        sale.payment_status = Sale.PaymentStatus.UNPAID

    sale.save(update_fields=["payment_status"])

    return paid_amount