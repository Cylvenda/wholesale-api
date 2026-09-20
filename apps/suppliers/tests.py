from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from .models import Supplier


class SupplierAPITests(TestCase):
    def test_authenticated_user_can_create_a_supplier_with_a_creator(self):
        user = User.objects.create_user(
            email="buyer@example.com",
            phone="255700000002",
            password="safe-password-123",
            role=User.Roles.MANAGER,
        )
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(
            "/api/suppliers/",
            {"name": "Supplier Ltd", "phone": "255700000003"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Supplier.objects.get().created_by, user)
