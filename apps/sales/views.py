from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import Sale, SaleItem
from .serializers import SaleSerializer
from ..stock.models import StockMovement
from ..stock.services import remove_stock, add_stock


class SaleViewSet(ModelViewSet):
    queryset = Sale.objects.prefetch_related("items").select_related("customer").order_by("-created_at")
    serializer_class = SaleSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    @transaction.atomic
    def perform_create(self, serializer):
        validated_data = serializer.validated_data
        items_data = validated_data.pop("items", [])

        if self.request.user.is_authenticated:
            validated_data["created_by"] = self.request.user

        sale = Sale.objects.create(
            **validated_data
        )

        total = Decimal("0.00")

        for item_data in items_data:
            quantity = item_data["quantity"]
            unit_price = item_data["unit_price"]
            product = item_data["product"]

            subtotal = quantity * unit_price

            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=subtotal,
                created_by=self.request.user
            )

            remove_stock(
                product=product,
                quantity=quantity,
                movement_type=StockMovement.MovementTypes.SALES,
                reference=str(sale.uuid),
                note=f"Sale {sale.uuid}",
                user=self.request.user
            )

            total += subtotal

        sale.subtotal = total
        sale.total = total - sale.discount
        sale.status = Sale.Status.COMPLETED

        sale.save(
            update_fields=["subtotal", "total", "status"]
        )

        serializer.instance = sale
        return sale

    @transaction.atomic
    def perform_update(self, serializer):
        sale = serializer.instance

        if sale.status != Sale.Status.COMPLETED:
            raise ValidationError("Only completed sales can be modified.")

        # Get new validated data
        validated_data = serializer.validated_data
        items_data = validated_data.pop("items", None)

        # Update Sale fields
        for field, value in validated_data.items():
            setattr(sale, field, value)

        sale.save()

        # If items were not included in the request,
        # there is no stock adjustment needed.
        if items_data is None:
            return

        # OLD ITEMS

        old_items = {
            item.product_id: item
            for item in sale.items.select_related("product")
        }

        # NEW ITEMS

        new_items = {
            item_data["product"].id: item_data
            for item_data in items_data
        }

        total = Decimal("0.00")

        # Process old + new products

        product_ids = set(old_items) | set(new_items)

        for product_id in product_ids:

            old_item = old_items.get(product_id)
            new_item = new_items.get(product_id)

            old_quantity = (
                old_item.quantity
                if old_item
                else 0
            )

            new_quantity = (
                new_item["quantity"]
                if new_item
                else 0
            )

            difference = new_quantity - old_quantity

            # Sale reduces stock.
            # Therefore:
            #
            # + difference → remove stock
            # - difference → add stock back

            if difference > 0:

                add_or_remove_quantity = difference

                remove_stock(
                    product=new_item["product"],
                    quantity=add_or_remove_quantity,
                    movement_type=StockMovement.MovementTypes.SALE_ADJUSTMENT,
                    reference=str(sale.uuid),
                    note="Sale quantity increased",
                    user=self.request.user,
                )

            elif difference < 0:

                add_or_add_back_quantity = abs(difference)

                product = (
                    old_item.product
                    if old_item
                    else new_item["product"]
                )

                add_stock(
                    product=product,
                    quantity=add_or_add_back_quantity,
                    movement_type=StockMovement.MovementTypes.SALE_ADJUSTMENT,
                    reference=str(sale.uuid),
                    note="Sale quantity decreased",
                    user=self.request.user,
                )

            # Calculate new total
            if new_item:
                total += (
                        new_item["quantity"]
                        * new_item["unit_price"]
                )

        # Replace SaleItems

        sale.items.all().delete()

        for item_data in items_data:
            quantity = item_data["quantity"]
            unit_price = item_data["unit_price"]

            SaleItem.objects.create(
                sale=sale,
                product=item_data["product"],
                quantity=quantity,
                unit_price=unit_price,
                subtotal=quantity * unit_price,
                created_by=self.request.user,
            )

        # Update sale total

        sale.subtotal = total
        sale.total = total - sale.discount

        sale.save(
            update_fields=["subtotal", "total"]
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    @transaction.atomic
    def cancel(self, request, uuid=None):
        sale = self.get_object()

        if sale.status == Sale.Status.CANCELLED:
            raise ValidationError(
                "This sale has already been cancelled."
            )

        if sale.status != Sale.Status.COMPLETED:
            raise ValidationError(
                "Only completed sales can be cancelled."
            )

        user = (
            request.user
            if request.user.is_authenticated
            else None
        )

        # Return sold products to stock
        for item in sale.items.select_related("product"):
            add_stock(
                product=item.product,
                quantity=item.quantity,
                movement_type=(
                    StockMovement
                    .MovementTypes.CANCEL
                ),
                reference=str(sale.uuid),
                note=f"Sale {sale.uuid} cancelled",
                user=user,
            )

        sale.status = Sale.Status.CANCELLED
        sale.save(update_fields=["status"])

        return Response(
            SaleSerializer(
                sale,
                context={"request": request}
            ).data,
            status=status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        raise ValidationError("Sales are immutable. Use the cancel action instead.")
