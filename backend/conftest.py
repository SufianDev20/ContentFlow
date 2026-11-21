import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.jobs.models import Job, Output
from apps.users.models import User


@pytest.fixture(autouse=True)
def _no_https_redirect(settings):
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture(autouse=True)
def _plain_static_files(settings):
    # The production manifest storage needs collectstatic to have run.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def _fresh_throttle_counters():
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="jane@example.com", password="pass12345!", full_name="Jane Doe"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="john@example.com", password="pass12345!", full_name="John Roe"
    )


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def make_job(user):
    def make(owner=None, **fields):
        fields.setdefault("content", "some blog content")
        fields.setdefault("model", "openai/gpt-4o")
        return Job.objects.create(user=owner or user, **fields)

    return make


@pytest.fixture
def make_output(make_job):
    def make(job=None, **fields):
        fields.setdefault("format", "email")
        fields.setdefault("text", "body")
        return Output.objects.create(job=job or make_job(), **fields)

    return make
