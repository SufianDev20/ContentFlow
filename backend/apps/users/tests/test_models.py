import pytest
from django.db import IntegrityError

from apps.users.models import User


def test_login_identifier_is_email(user):
    assert User.USERNAME_FIELD == "email"
    assert User.objects.get_by_natural_key("jane@example.com") == user


def test_password_is_stored_hashed(user):
    assert user.password != "pass12345!"
    assert user.check_password("pass12345!")


def test_email_is_unique(user):
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="jane@example.com", password="x", full_name="Dup")


def test_email_is_required(db):
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="x", full_name="Nobody")


def test_superuser_is_staff_and_superuser(db):
    admin = User.objects.create_superuser(email="a@example.com", password="x", full_name="A")

    assert admin.is_staff and admin.is_superuser


def test_new_user_gets_a_profile_with_no_model_preference(user):
    assert user.profile.default_model == ""
