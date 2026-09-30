from django.test import TestCase

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
