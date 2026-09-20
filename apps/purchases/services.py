from django.db import transaction

from ..stock.models import StockMovement
from ..stock.services import add_stock, remove_stock


class PurchaseService:
    """Helpers for keeping stock in sync when purchase items change."""

    @staticmethod
    @transaction.atomic
    def update_purchase_item(purchase_item, old_quantity, old_product, user=None):
        """
        Adjust stock when a purchase item is updated.

        - If the product changed, reverse the old allocation and apply the new one.
        - If the product stayed the same, only adjust the difference.

        Draft purchases do not affect stock; only completed purchases
        trigger stock adjustments.
        """

        new_quantity = purchase_item.quantity
        new_product = purchase_item.product

        reference = str(purchase_item.purchase.uuid)

        # Only completed purchases affect stock.
        if purchase_item.purchase.status != purchase_item.purchase.Status.COMPLETED:
            return

        if old_product != new_product:
            remove_stock(
                product=old_product,
                quantity=old_quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=reference,
                note=f"Reversing previous purchase item {purchase_item.uuid}",
                user=user,
            )

            add_stock(
                product=new_product,
                quantity=new_quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=reference,
                note=f"Purchase {purchase_item.purchase.uuid} updated",
                user=user,
            )

        else:
            difference = new_quantity - old_quantity

            if difference > 0:
                add_stock(
                    product=new_product,
                    quantity=difference,
                    movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                    reference=reference,
                    note=f"Purchase {purchase_item.purchase.uuid} increased",
                    user=user,
                )

            elif difference < 0:
                remove_stock(
                    product=new_product,
                    quantity=abs(difference),
                    movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                    reference=reference,
                    note=f"Purchase {purchase_item.purchase.uuid} decreased",
                    user=user,
                )
