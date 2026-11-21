from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.jobs.models import Job
from apps.users.models import User

PASSWORD = "pass12345!"


def register_payload(**overrides):
    return {
        "email": "new@example.com",
        "full_name": "New User",
        "password": "a-Strong-pass-9",
        **overrides,
    }


class TestRegister:
    url = reverse("auth-register")

    def test_creates_user_without_echoing_password(self, db):
        response = APIClient().post(self.url, register_payload())

        assert response.status_code == 201
        assert "password" not in response.data
        assert User.objects.get(email="new@example.com").check_password("a-Strong-pass-9")

    @pytest.mark.parametrize(
        "overrides",
        [{"email": "not-an-email"}, {"full_name": ""}, {"password": "short"}, {"password": "12345678"}],
    )
    def test_invalid_input_is_rejected(self, db, overrides):
        assert APIClient().post(self.url, register_payload(**overrides)).status_code == 400
        assert not User.objects.exists()

    def test_duplicate_email_is_rejected(self, user):
        response = APIClient().post(self.url, register_payload(email=user.email))

        assert response.status_code == 400


class TestLogin:
    url = reverse("auth-login")

    def test_sets_httponly_jwt_cookies_and_returns_the_user(self, user):
        response = APIClient().post(self.url, {"email": user.email, "password": PASSWORD})

        assert response.status_code == 200
        assert response.data["email"] == user.email
        assert "access" not in response.data
        for name in (settings.SIMPLE_JWT["AUTH_COOKIE"], settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"]):
            assert response.cookies[name]["httponly"]

    def test_cookie_session_can_call_authenticated_endpoints(self, user):
        client = APIClient()
        client.post(self.url, {"email": user.email, "password": PASSWORD})

        assert client.get(reverse("auth-me")).data["email"] == user.email

    @pytest.mark.parametrize(
        "email,password", [("jane@example.com", "wrong"), ("nobody@example.com", PASSWORD)]
    )
    def test_bad_credentials_are_rejected(self, user, email, password):
        response = APIClient().post(self.url, {"email": email, "password": password})

        assert response.status_code == 401
        assert not response.cookies

    def test_inactive_user_cannot_log_in(self, user):
        user.is_active = False
        user.save()

        response = APIClient().post(self.url, {"email": user.email, "password": PASSWORD})

        assert response.status_code == 401


class TestSession:
    def login(self, user):
        client = APIClient()
        client.post(reverse("auth-login"), {"email": user.email, "password": PASSWORD})
        return client

    def test_me_requires_authentication(self, db):
        assert APIClient().get(reverse("auth-me")).status_code == 401

    def test_garbage_token_is_rejected(self, db):
        client = APIClient()
        client.cookies[settings.SIMPLE_JWT["AUTH_COOKIE"]] = "garbage"

        assert client.get(reverse("auth-me")).status_code == 401

    def test_refresh_issues_a_new_access_cookie(self, user):
        client = self.login(user)

        response = client.post(reverse("auth-token-refresh"))

        assert response.status_code == 200
        assert settings.SIMPLE_JWT["AUTH_COOKIE"] in response.cookies

    def test_refresh_without_cookie_is_unauthorized(self, db):
        assert APIClient().post(reverse("auth-token-refresh")).status_code == 401

    def test_logout_blacklists_refresh_token_and_clears_cookies(self, user):
        client = self.login(user)
        refresh = client.cookies[settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"]].value

        response = client.post(reverse("auth-logout"))

        assert response.status_code == 204
        assert response.cookies[settings.SIMPLE_JWT["AUTH_COOKIE"]].value == ""
        client.cookies[settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"]] = refresh
        assert client.post(reverse("auth-token-refresh")).status_code == 401


class TestProfile:
    url = reverse("auth-profile")

    def test_updates_name_and_default_model(self, api, user):
        with patch(
            "apps.users.serializers.llm.available_models",
            return_value={"openrouter": ["vendor/model:free"], "gemini": []},
        ):
            response = api.patch(
                self.url, {"full_name": "Jane Q", "default_model": "vendor/model:free"}
            )

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.full_name == "Jane Q"
        assert user.profile.default_model == "vendor/model:free"

    def test_default_model_must_be_a_currently_available_model(self, api, user):
        with patch(
            "apps.users.serializers.llm.available_models",
            return_value={"openrouter": ["vendor/model:free"], "gemini": []},
        ):
            response = api.patch(self.url, {"default_model": "not/available"})

        assert response.status_code == 400
        user.profile.refresh_from_db()
        assert user.profile.default_model == ""

    def test_empty_default_model_clears_the_preference(self, api, user):
        user.profile.default_model = "x"
        user.profile.save()

        assert api.patch(self.url, {"default_model": ""}).status_code == 200
        user.profile.refresh_from_db()
        assert user.profile.default_model == ""


class TestAccountDelete:
    url = reverse("auth-account-delete")

    def test_requires_the_current_password(self, api, user):
        response = api.delete(self.url, {"password": "wrong"})

        assert response.status_code == 400
        assert User.objects.filter(pk=user.pk).exists()

    def test_deletes_user_their_jobs_and_clears_cookies(self, api, user, make_job):
        make_job()

        response = api.delete(self.url, {"password": PASSWORD})

        assert response.status_code == 204
        assert not User.objects.filter(pk=user.pk).exists()
        assert response.cookies[settings.SIMPLE_JWT["AUTH_COOKIE"]].value == ""
        assert not Job.objects.exists()
