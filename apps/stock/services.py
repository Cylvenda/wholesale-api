"""Single source of truth for stock maths.

Stock is stored in whole BASE units.  A ``ProductUnit.conversion_factor`` says
how many base units are inside one of that unit, so everything a user sees for
a *selected* selling unit is derived here with integer arithmetic only:

    base_stock = 239, conversion_factor = 24
    whole_quantity = 239 // 24 = 9 crates
    remainder      = 239 % 24  = 23 base units
    display        = "9 Crates + 23 Chupa"
"""

from decimal import Decimal

from django.db import transaction
from .models import StockMovement, Stock
from apps.products.models import ProductUnit


def _factor(value) -> int:
    """Coerce a stored/loose conversion factor to a whole number >= 1."""
    factor = int(value)
    if factor < 1:
        raise ValueError("Conversion factor must be a whole number of at least 1.")
    return factor


def whole_quantity(value, conversion_factor) -> int:
    """How many whole units of ``conversion_factor`` fit into ``value`` base units."""
    return int(value) // _factor(conversion_factor)


def remainder_quantity(value, conversion_factor) -> int:
    """Base units left over after taking out every whole pack."""
    return int(value) % _factor(conversion_factor)


def convert_to_base_quantity(product_unit, quantity) -> int:
    """Convert a whole transaction quantity into whole base units."""
    factor = _factor(product_unit.conversion_factor)
    return int(quantity) * factor


def create_stock(product):
    return Stock.objects.create(product=product, quantity=0)


def get_base_unit_config(product):
    """Get the ProductUnit configuration for the product's base unit."""
    return ProductUnit.objects.filter(
        product=product,
        unit=product.base_unit,
        is_active=True,
    ).first()


def validate_whole_quantity(quantity):
    """Inventory quantities are whole positive numbers.  No fractional units."""
    if isinstance(quantity, bool):
        raise ValueError("Quantity must be a whole number greater than zero.")
    try:
        whole = int(quantity)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantity must be a whole number greater than zero.") from exc
    if isinstance(quantity, float) and quantity != whole:
        raise ValueError("Quantity must be a whole number, not a fraction.")
    if whole <= 0:
        raise ValueError("Quantity must be a whole number greater than zero.")
    return whole


def validate_product_unit(product, product_unit):
    """A product unit must be an active configuration of this exact product."""
    if product_unit is None:
        raise ValueError("Select a selling unit for this product.")
    if product_unit.product_id != product.pk:
        raise ValueError("Selected unit is not configured for this product.")
    if not product_unit.is_active:
        raise ValueError("Selected unit is no longer available for this product.")
    _factor(product_unit.conversion_factor)
    return product_unit


def base_stock_for(product) -> int:
    stock = Stock.objects.filter(product=product).first()
    return int(stock.quantity) if stock else 0


def availability(product, product_unit, base_stock=None) -> dict:
    """Represent base stock in terms of the selected selling unit.

    Returns the payload consumed by the stock table, the sale form and the
    availability endpoint so every surface shows the same thing.
    """
    base_unit = product.base_unit
    stock = base_stock_for(product) if base_stock is None else int(base_stock)

    if product_unit is None:
        return {
            "base_stock": stock,
            "base_unit": base_unit.name,
            "base_unit_abbreviation": base_unit.abbreviation,
            "selected_unit": None,
            "conversion_factor": None,
            "available_quantity": stock,
            "remainder_base_quantity": 0,
            "available_display": f"{stock} {base_unit.abbreviation or base_unit.name}",
            "base_display": f"{stock} {base_unit.abbreviation or base_unit.name}",
        }

    factor = _factor(product_unit.conversion_factor)
    unit_label = product_unit.unit.abbreviation or product_unit.unit.name
    base_label = base_unit.abbreviation or base_unit.name
    whole = whole_quantity(stock, factor)
    remainder = remainder_quantity(stock, factor)

    if factor == 1:
        display = f"{whole} {base_label}"
    elif remainder:
        display = f"{whole} {unit_label} + {remainder} {base_label}"
    else:
        display = f"{whole} {unit_label}"

    return {
        "base_stock": stock,
        "base_unit": base_unit.name,
        "base_unit_abbreviation": base_unit.abbreviation,
        "selected_unit": product_unit.unit.name,
        "conversion_factor": factor,
        "available_quantity": whole,
        "remainder_base_quantity": remainder,
        "available_display": display,
        "base_display": f"{stock} {base_label}",
    }


def insufficient_stock_message(product, product_unit, requested_quantity, base_stock=None):
    """Message that explains exactly what is available in the selected unit."""
    info = availability(product, product_unit, base_stock)
    unit_label = (
        (product_unit.unit.abbreviation or product_unit.unit.name)
        if product_unit
        else product.base_unit.abbreviation or product.base_unit.name
    )
    requested_base = (
        int(requested_quantity) * _factor(product_unit.conversion_factor)
        if product_unit
        else int(requested_quantity)
    )
    return (
        f"Insufficient stock. Available: {info['base_display']} "
        f"({info['available_display']}). "
        f"Requested: {int(requested_quantity)} {unit_label} ({requested_base} {info['base_unit']})."
    )


def validate_stock(product, required_base_quantity, product_unit=None, requested_quantity=None):
    """Validate that the required whole base quantity is actually on hand."""
    stock = Stock.objects.filter(product=product).first()
    if stock is None:
        raise ValueError(f"No stock record found for {product.name}.")
    required_base_quantity = int(required_base_quantity)
    if stock.quantity < required_base_quantity:
        if requested_quantity is not None and product_unit is not None:
            raise ValueError(
                insufficient_stock_message(
                    product, product_unit, requested_quantity, stock.quantity
                )
            )
        raise ValueError(
            f"Insufficient stock for {product.name}. "
            f"Available: {stock.quantity} {product.base_unit.name}. "
            f"Required: {required_base_quantity} {product.base_unit.name}."
        )
    return True


def ensure_sale_quantity(product, product_unit, quantity, stock=None):
    """Full backend gate for selling: whole quantity, valid unit, enough stock.

    Returns the base quantity to remove from stock.
    """
    whole_quantity_value = validate_whole_quantity(quantity)
    validate_product_unit(product, product_unit)

    if not product.is_active:
        raise ValueError(f"{product.name} is not an active product.")

    base_quantity = convert_to_base_quantity(product_unit, whole_quantity_value)
    if base_quantity <= 0:
        raise ValueError("Quantity converts to zero base units. Check the conversion factor.")

    validate_stock(
        product,
        base_quantity,
        product_unit=product_unit,
        requested_quantity=whole_quantity_value,
    )
    return base_quantity


@transaction.atomic
def add_stock(
    *,
    product,
    base_quantity,
    movement_type,
    reference="",
    note="",
    user=None,
    # Transaction unit info for audit trail
    transaction_unit=None,
    transaction_quantity=None,
    conversion_factor_used=None,
):
    base_quantity = int(base_quantity)
    if base_quantity <= 0:
        raise ValueError("Quantity must be a whole number greater than zero.")

    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=product,
        defaults={"quantity": 0, "created_by": user},
    )

    stock.quantity = int(stock.quantity) + base_quantity
    stock.save(update_fields=["quantity"])

    base_unit = product.base_unit

    movement = StockMovement.objects.create(
        stock=stock,
        quantity=base_quantity,
        movement_type=movement_type,
        reference=reference,
        notes=note,
        created_by=user,
        # Transaction unit tracking
        transaction_unit=transaction_unit,
        transaction_quantity=(
            int(transaction_quantity) if transaction_quantity is not None else None
        ),
        transaction_unit_name=transaction_unit.name if transaction_unit else base_unit.name,
        conversion_factor_used=(
            int(conversion_factor_used) if conversion_factor_used is not None else None
        ),
        base_unit=base_unit,
        base_quantity=base_quantity,
        base_unit_name=base_unit.name,
    )

    return stock, movement


@transaction.atomic
def remove_stock(
    *,
    product,
    base_quantity,
    movement_type,
    reference="",
    note="",
    user=None,
    # Transaction unit info for audit trail
    transaction_unit=None,
    transaction_quantity=None,
    conversion_factor_used=None,
):
    base_quantity = int(base_quantity)
    if base_quantity <= 0:
        raise ValueError("Quantity must be a whole number greater than zero.")

    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=product,
        defaults={"quantity": 0, "created_by": user},
    )

    if stock.quantity < base_quantity:
        raise ValueError(
            f"Insufficient stock for {product.name}. "
            f"Available: {stock.quantity} {product.base_unit.name}. "
            f"Required: {base_quantity} {product.base_unit.name}."
        )

    stock.quantity = int(stock.quantity) - base_quantity
    stock.save(update_fields=["quantity"])

    base_unit = product.base_unit

    movement = StockMovement.objects.create(
        stock=stock,
        quantity=base_quantity,
        movement_type=movement_type,
        reference=reference,
        notes=note,
        created_by=user,
        # Transaction unit tracking
        transaction_unit=transaction_unit,
        transaction_quantity=(
            int(transaction_quantity) if transaction_quantity is not None else None
        ),
        transaction_unit_name=transaction_unit.name if transaction_unit else base_unit.name,
        conversion_factor_used=(
            int(conversion_factor_used) if conversion_factor_used is not None else None
        ),
        base_unit=base_unit,
        base_quantity=base_quantity,
        base_unit_name=base_unit.name,
    )

    return stock, movement


def largest_pack_unit(product):
    """Biggest configured pack unit for the product, used for readable display."""
    return (
        ProductUnit.objects.filter(product=product, is_active=True)
        .exclude(conversion_factor=1)
        .order_by("-conversion_factor")
        .first()
    )


def base_unit_price(product):
    """Buying price of one BASE unit of the product.

    Stock is counted in base units, so its money value must be priced with the
    base unit's own configured ``ProductUnit.buying_price`` - not a pack price
    and not the legacy ``Product.buying_price`` mirror, which goes stale as soon
    as the unit table is edited.
    """
    base_config = get_base_unit_config(product)
    if base_config is not None:
        return base_config.buying_price
    return product.buying_price or Decimal("0.00")


def stock_value(stocks) -> Decimal:
    """Total money value of the given Stock rows, in base units."""
    total = Decimal("0.00")
    for stock in stocks:
        total += int(stock.quantity) * base_unit_price(stock.product)
    return total


def format_stock_quantity(product, base_quantity):
    """Human readable stock, e.g. ``9 CS + 23 Chupa`` for 239 base units."""
    base_quantity = max(int(base_quantity), 0)
    base_unit = product.base_unit
    base_label = base_unit.abbreviation or base_unit.name

    pack = largest_pack_unit(product)
    if pack is None:
        return f"{base_quantity} {base_label}"

    factor = _factor(pack.conversion_factor)
    pack_label = pack.unit.abbreviation or pack.unit.name
    packs = base_quantity // factor
    remainder = base_quantity % factor

    # A pack is only ever sold or counted whole, so leftover base units are
    # always spelled out: 23 bottles read as "0 CS + 23 Chupa".
    if not remainder:
        return f"{packs} {pack_label}"
    return f"{packs} {pack_label} + {remainder} {base_label}"