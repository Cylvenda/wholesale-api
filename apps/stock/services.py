from django.db import transaction
from .models import StockMovement, Stock


def create_stock(product):
    return Stock.objects.create(
        product=product,
        quantity=0,
    )


@transaction.atomic
def add_stock(
    *,
    product,
    quantity,
    movement_type,
    reference="",
    note="",
    user=None,
):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=product,
        defaults={"created_by": user},
    )

    stock.quantity += quantity
    stock.save(update_fields=["quantity"])

    StockMovement.objects.create(
        stock=stock,
        quantity=quantity,
        movement_type=movement_type,
        reference=reference,
        notes=note,
        created_by=user,
    )

    return stock


@transaction.atomic
def remove_stock(
    *,
    product,
    quantity,
    movement_type,
    reference="",
    note="",
    user=None,
):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=product,
        defaults={"created_by": user},
    )

    if stock.quantity < quantity:
        raise ValueError(
            f"Insufficient stock for {product.name}."
        )

    stock.quantity -= quantity
    stock.save(update_fields=["quantity"])

    StockMovement.objects.create(
        stock=stock,
        quantity=quantity,
        movement_type=movement_type,
        reference=reference,
        notes=note,
        created_by=user,
    )

    return stock