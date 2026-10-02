from django.test import TestCase
from rest_framework.test import APIClient

from apps.products.models import Brand, Category, Product, Unit
from .models import User
from .serializers import UserCreateSerializer


class UserCreatePasswordValidationTests(TestCase):
    def make_payload(self, password):
        return {
            "email": "new.user@example.com",
            "phone": "+255700000001",
            "first_name": "New",
            "last_name": "User",
            "password": password,
            "role": "salesperson",
            "is_active": True,
        }

    def test_rejects_password_missing_required_character_types(self):
        serializer = UserCreateSerializer(data=self.make_payload("alllowercase1!"))

        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)

    def test_accepts_password_matching_requirements(self):
        serializer = UserCreateSerializer(data=self.make_payload("GoodPass1!"))

        self.assertTrue(serializer.is_valid(), serializer.errors)


class UserDeletionTests(TestCase):
    """Deleting a user used to blow up as a 500 from ProtectedError."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            phone="255700000021",
            password="Admin@12345",
            role=User.Roles.ADMIN,
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def make_user(self, email="victim@example.com", phone="255700000022"):
        return User.objects.create_user(
            email=email, phone=phone, password="Victim@12345"
        )

    def test_creator_of_records_is_rejected_with_a_readable_reason(self):
        user = self.make_user()
        category = Category.objects.create(name="Drinks", created_by=user)
        brand = Brand.objects.create(name="Brand", category=category, created_by=user)
        unit = Unit.objects.create(name="Bottle", abbreviation="BTL", created_by=user)
        Product.objects.create(
            brand=brand,
            base_unit=unit,
            name="Juice",
            buying_price="1.00",
            selling_price="2.00",
            created_by=user,
        )

        response = self.client.delete(f"/api/users/{user.uuid}/")

        self.assertEqual(response.status_code, 400)
        message = str(response.data)
        self.assertIn("cannot be deleted", message)
        self.assertIn("product", message)
        self.assertIn("history stays intact", message)
        # Nothing was destroyed by the failed attempt.
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_user_without_records_is_deleted(self):
        user = self.make_user()

        response = self.client.delete(f"/api/users/{user.uuid}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_admin_cannot_delete_their_own_account(self):
        response = self.client.delete(f"/api/users/{self.admin.uuid}/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("signed in with", str(response.data))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())


class StaffFlagFollowsRoleTests(TestCase):
    """``role="admin"`` must grant the staff flag the permissions read."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="root@example.com",
            phone="255700000031",
            password="Root@123456",
            role=User.Roles.ADMIN,
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_creating_an_admin_marks_them_staff(self):
        response = self.client.post(
            "/api/users/",
            {
                "email": "second.admin@example.com",
                "phone": "255700000032",
                "password": "Second@12345",
                "role": "admin",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="second.admin@example.com")
        self.assertEqual(user.role, User.Roles.ADMIN)
        self.assertTrue(user.is_staff)

    def test_demoting_an_admin_clears_the_staff_flag(self):
        user = User.objects.create_user(
            email="demoted@example.com",
            phone="255700000033",
            password="Demote@12345",
            role=User.Roles.ADMIN,
        )
        # Created directly, so the flag has not been synced yet.
        User.objects.filter(pk=user.pk).update(is_staff=False)

        response = self.client.patch(
            f"/api/users/{user.uuid}/", {"role": "salesperson"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Roles.SALESPERSON)
        self.assertFalse(user.is_staff)
