"""
apps/users/tests/test_views.py

Test cases for auth endpoints: register, login, me.
Assumes:
- POST /api/v1/auth/register/
- POST /api/v1/auth/login/  (TokenObtainPairView subclass)
- GET  /api/v1/auth/me/
Adjust URL names/paths to match your urls.py.
"""

from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.users.models import User


class RegisterViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("register")  # adjust name to match urls.py

    def test_register_with_valid_data_creates_user(self):
        payload = {
            "email": "jane@example.com",
            "password": "StrongPass123!",
            "full_name": "Jane Doe",
        }
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="jane@example.com").exists())

    def test_register_with_duplicate_email_fails(self):
        User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane"
        )
        payload = {
            "email": "jane@example.com",
            "password": "StrongPass123!",
            "full_name": "Jane Doe",
        }
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_with_missing_full_name_fails(self):
        payload = {"email": "jane@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_with_invalid_email_format_fails(self):
        payload = {
            "email": "not-an-email",
            "password": "StrongPass123!",
            "full_name": "Jane Doe",
        }
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_response_does_not_return_password(self):
        payload = {
            "email": "jane@example.com",
            "password": "StrongPass123!",
            "full_name": "Jane Doe",
        }
        response = self.client.post(self.url, payload)
        self.assertNotIn("password", response.data)


class LoginViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("login")  # adjust name to match urls.py
        self.user = User.objects.create_user(
            email="jane@example.com", password="StrongPass123!", full_name="Jane Doe"
        )

    def test_login_with_valid_credentials_returns_tokens(self):
        payload = {"email": "jane@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_with_wrong_password_fails(self):
        payload = {"email": "jane@example.com", "password": "WrongPass"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_nonexistent_email_fails(self):
        payload = {"email": "ghost@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_inactive_user_fails(self):
        self.user.is_active = False
        self.user.save()
        payload = {"email": "jane@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("me")  # adjust name to match urls.py
        self.user = User.objects.create_user(
            email="jane@example.com", password="StrongPass123!", full_name="Jane Doe"
        )

    def test_me_without_token_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_valid_token_returns_user_data(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "jane@example.com")
        self.assertEqual(response.data["full_name"], "Jane Doe")
        self.assertIn("theme_preference", response.data)
        self.assertIn("profile_image", response.data)

    def test_me_with_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalidtoken123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
