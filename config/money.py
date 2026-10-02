"""Money helpers shared by every endpoint that reports a total.

SQLite returns ``SUM()`` over a ``DecimalField`` with an unscaled result: adding
``0.10`` gives ``Decimal("0.100000000000000")``. Left alone, that garbage scale
propagates into balances and is printed to the user, so every aggregate that
feeds money is normalised to the field's own precision here.
"""

from decimal import Decimal, InvalidOperation

# DecimalField(max_digits=12, decimal_places=2) is used for all money.
MONEY_PLACES = Decimal("0.01")


def to_money(value) -> Decimal:
    """Coerce any aggregate or loose value to exact 2-decimal money."""
    if value is None:
        return Decimal("0.00")
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")
    return value.quantize(MONEY_PLACES)


def money_sum(values) -> Decimal:
    """Sum money values without letting float rounding creep in."""
    total = Decimal("0.00")
    for value in values:
        total += to_money(value)
    return total