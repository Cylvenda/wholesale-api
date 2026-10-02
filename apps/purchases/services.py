from django.db import transaction
from config.reference_codes import format_reference

from ..stock.models import StockMovement
from ..stock.services import add_stock, remove_stock


class PurchaseService:
    """Helpers for keeping stock in sync when purchase items change."""

    @staticmethod
    @transaction.atomic
    def update_purchase_item(purchase_item, old_base_quantity, old_product, user=None):
        """
        Adjust stock when a purchase item is updated.

        - If the product changed, reverse the old allocation and apply the new one.
        - If the product stayed the same, only adjust the difference.

        ``old_base_quantity`` is always a whole number of base units; the
        conversion has already been applied by the caller.

        Draft purchases do not affect stock; only completed purchases
        trigger stock adjustments.
        """

        new_base_quantity = int(purchase_item.base_quantity)
        new_product = purchase_item.product
        old_base_quantity = int(old_base_quantity)

        reference = format_reference("PUR", purchase_item.purchase.pk)

        # Only completed purchases affect stock.
        if purchase_item.purchase.status != purchase_item.purchase.Status.COMPLETED:
            return

        if old_product != new_product:
            remove_stock(
                product=old_product,
                base_quantity=old_base_quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=reference,
                note="Reversing previous purchase item",
                user=user,
            )

            add_stock(
                product=new_product,
                base_quantity=new_base_quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=reference,
                note=f"Purchase {reference} updated",
                user=user,
            )

        else:
            difference = new_base_quantity - old_base_quantity

            if difference > 0:
                add_stock(
                    product=new_product,
                    base_quantity=difference,
                    movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                    reference=reference,
                    note=f"Purchase {reference} increased",
                    user=user,
                )

            elif difference < 0:
                remove_stock(
                    product=new_product,
                    base_quantity=abs(difference),
                    movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                    reference=reference,
                    note=f"Purchase {reference} decreased",
                    user=user,
                )