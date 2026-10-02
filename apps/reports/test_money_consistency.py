"""Money must read the same on every page that reports it.

These tests deliberately touch several endpoints for one small set of
transactions and assert that each surface reports identical money. They also
guard the two defects that made pages disagree:

* SQLite returns ``SUM()`` over a DecimalField unscaled
  (``Decimal("0.100000000000000")``), which leaked junk digits into balances.
* Stock value was priced from the legacy ``Product.buying_price`` mirror instead
  of the base unit's configured ``ProductUnit.buying_price``.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.products.models import (
    Brand,
    Category,
    Product,
    ProductUnit,
    Unit,
)
from apps.purchases.models import Purchase, PurchaseItem
from apps.sales.models import Sale, SaleItem
from apps.stock.models import Stock
from apps.suppliers.models import Supplier
from config.money import to_money


class MoneyConsistencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            phone="255700000088",
            password="safe-password-123",
            role=User.Roles.MANAGER,
        )
        category = Category.objects.create(name="Drinks", created_by=self.user)
        self.brand = Brand.objects.create(
            name="Mirinda", category=category, created_by=self.user
        )
        self.bottle = Unit.objects.create(
            name="Chupa ya Soda", abbreviation="CHP", created_by=self.user
        )
        self.crate = Unit.objects.create(
            name="Crate ya Soda", abbreviation="CS", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Mirinda Orange",
            # Deliberately stale: the unit table below is the source of truth.
            buying_price=Decimal("999.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        self.base_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.bottle,
            conversion_factor=1,
            buying_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            created_by=self.user,
        )
        self.crate_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.crate,
            conversion_factor=24,
            buying_price=Decimal("11000.00"),
            selling_price=Decimal("15000.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=self.product, created_by=self.user)
        self.supplier = Supplier.objects.create(
            name="Distributors Ltd",
            phone="255712000199",
            created_by=self.user,
        )
        self.customer = Customer.objects.create(
            name="Shop Owner", created_by=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def record_purchase(self, quantity=10, unit_cost="11000.00"):
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            status=Purchase.Status.COMPLETED,
            purchase_date=timezone.now(),
            created_by=self.user,
        )
        subtotal = quantity * Decimal(unit_cost)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            product_unit=self.crate_config,
            quantity=quantity,
            conversion_factor_used=24,
            base_quantity=quantity * 24,
            unit_cost=Decimal(unit_cost),
            subtotal=subtotal,
            unit_name=self.crate.name,
            unit_abbreviation=self.crate.abbreviation,
            product_name=self.product.name,
            created_by=self.user,
        )
        purchase.total = subtotal
        purchase.save(update_fields=["total"])
        Stock.objects.filter(product=self.product).update(
            quantity=quantity * 24
        )
        return purchase

    def record_sale(self, quantity=2, unit_price="15000.00"):
        sale = Sale.objects.create(
            customer=self.customer,
            status=Sale.Status.COMPLETED,
            subtotal=quantity * Decimal(unit_price),
            total=quantity * Decimal(unit_price),
            sale_date=timezone.now(),
            created_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_unit=self.crate_config,
            quantity=quantity,
            conversion_factor_used=24,
            base_quantity=quantity * 24,
            unit_price=Decimal(unit_price),
            subtotal=quantity * Decimal(unit_price),
            unit_name=self.crate.name,
            unit_abbreviation=self.crate.abbreviation,
            product_name=self.product.name,
            created_by=self.user,
        )
        return sale

    def test_stock_value_uses_the_base_unit_price_not_the_stale_product_price(self):
        """240 bottles x the base unit's 500, never the stale 999 mirror."""
        self.record_purchase(quantity=10)

        summary = self.client.get("/api/stocks/summary/").data
        stock_row = self.client.get("/api/stocks/").data["results"][0]

        self.assertEqual(summary["stock_value"], "120000.00")
        # 240 base units x 500.00
        self.assertEqual(stock_row["buying_price"], "500.00")
        self.assertEqual(stock_row["quantity"], 240)

    def test_purchase_money_agrees_across_summary_row_and_receipt(self):
        purchase = self.record_purchase(quantity=10)

        listed = self.client.get(f"/api/purchases/{purchase.uuid}/").data
        supplier_summary = self.client.get("/api/suppliers/summary/").data
        dashboard = self.client.get("/api/dashboard/?period=all").data

        self.assertEqual(str(listed["total"]), "110000.00")
        self.assertEqual(str(listed["items"][0]["subtotal"]), "110000.00")
        self.assertEqual(
            to_money(supplier_summary["total_purchases"]),
            to_money(purchase.total),
        )
        self.assertEqual(
            to_money(dashboard["purchases_value"]), to_money(purchase.total)
        )

    def test_sale_money_agrees_across_summary_row_and_dashboard(self):
        sale = self.record_sale(quantity=2)

        listed = self.client.get(f"/api/sales/{sale.uuid}/").data
        customer_summary = self.client.get("/api/customers/summary/").data
        dashboard = self.client.get("/api/dashboard/?period=all").data

        self.assertEqual(to_money(listed["total"]), to_money(sale.total))
        self.assertEqual(
            to_money(customer_summary["total_sales"]), to_money(sale.total)
        )
        self.assertEqual(to_money(dashboard["sales_value"]), to_money(sale.total))

    def test_sale_deducts_money_and_purchase_adds_stock_value(self):
        """A sale must reduce the same stock the purchase added."""
        self.record_purchase(quantity=10)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 240)

        sale = self.record_sale(quantity=2)
        Stock.objects.filter(product=self.product).update(quantity=240 - 48)

        dashboard = self.client.get("/api/dashboard/?period=all").data
        summary = self.client.get("/api/stocks/summary/").data

        # 192 bottles left, still valued with the base unit price of 500.
        self.assertEqual(summary["stock_value"], "96000.00")
        self.assertEqual(to_money(dashboard["sales_value"]), to_money(sale.total))

    def test_no_money_total_ever_carries_stray_decimal_digits(self):
        """SQLite SUM returns unscaled decimals; none may reach the client."""
        self.record_purchase(quantity=3, unit_cost="1000.50")
        sale = self.record_sale(quantity=1, unit_price="700.25")

        from apps.payments.models import Payment

        Payment.objects.create(
            customer=self.customer,
            sale=sale,
            amount=Decimal("200.10"),
            method="cash",
            payment_date=timezone.now(),
            created_by=self.user,
        )
        from apps.payments.services import update_sale_payment_status

        update_sale_payment_status(sale)

        payloads = [
            self.client.get("/api/payments/summary/").data,
            self.client.get("/api/customers/summary/").data,
            self.client.get("/api/suppliers/summary/").data,
            self.client.get("/api/stocks/summary/").data,
            self.client.get("/api/dashboard/?period=all").data,
        ]

        for payload in payloads:
            for key, value in payload.items():
                if not isinstance(value, str):
                    continue
                try:
                    amount = Decimal(value)
                except Exception:
                    continue
                # Exactly two decimal places, never "0.200000000000000".
                self.assertEqual(
                    -amount.as_tuple().exponent,
                    2,
                    f"{key}={value} carries stray decimal digits",
                )