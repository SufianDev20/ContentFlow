import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    "name",
    ["index", "login", "register", "dashboard", "settings", "profile", "history", "job", "stats"],
)
def test_page_renders(client, name):
    assert client.get(reverse(name)).status_code == 200


def test_logout_page_redirects_to_login(client):
    response = client.get(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")


def test_sentry_debug_route_is_not_exposed_outside_debug(client):
    assert client.get("/sentry-debug/").status_code == 404
