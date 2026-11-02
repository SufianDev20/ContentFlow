"""
apps/users/tests/test_models.py

Covers the custom User model per PRD 8.1.
Fields: id (UUID), email (unique), full_name (100), password, created_at, is_active.
USERNAME_FIELD = 'email'. username removed via username = None.
"""

from django.db import IntegrityError
from django.test import TestCase
from apps.users.models import User


class UserModelTests(TestCase):
    def test_create_user_with_email_and_password(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.assertEqual(user.email, "jane@example.com")
        self.assertTrue(user.check_password("pass123"))

    def test_id_is_uuid(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.assertEqual(len(str(user.id)), 36)

    def test_email_is_unique(self):
        User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email="jane@example.com", password="other123", full_name="Jane Two"
            )

    def test_username_field_is_email(self):
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_required_fields_includes_full_name(self):
        self.assertIn("full_name", User.REQUIRED_FIELDS)

    def test_username_attribute_does_not_exist(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.assertIsNone(user.username)

    def test_is_active_defaults_to_true(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.assertTrue(user.is_active)

    def test_full_name_max_length_is_100(self):
        field = User._meta.get_field("full_name")
        self.assertEqual(field.max_length, 100)

    def test_password_is_hashed_not_plaintext(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.assertNotEqual(user.password, "pass123")

    def test_created_at_is_set_automatically(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.assertIsNotNone(user.created_at)

    def test_str_representation_is_email_or_full_name(self):
        user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        # Adjust this assertion if __str__ is not overridden to include email.
        self.assertIn("jane@example.com", str(user))

    def test_create_superuser_sets_staff_and_superuser_flags(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pass123", full_name="Admin User"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_profile_fields_have_expected_defaults(self):
        user = User.objects.create_user(
            email="profile@example.com", password="pass123", full_name="Profile User"
        )
        self.assertEqual(user.theme_preference, "dark")
        self.assertEqual(user.background_color, "#0f172a")
        self.assertEqual(user.display_name, "")
        self.assertEqual(user.default_model, "")
        self.assertFalse(user.profile_image)
