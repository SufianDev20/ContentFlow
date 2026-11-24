from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from . import views


def page(route, template, name):
    return path(route, TemplateView.as_view(template_name=template), name=name)


urlpatterns = [
    page("", "index.html", "index"),
    page("login/", "login.html", "login"),
    page("register/", "register.html", "register"),
    path("logout/", RedirectView.as_view(pattern_name="login"), name="logout"),
    page("dashboard/", "dashboard.html", "dashboard"),
    page("settings/", "dashboard.html", "settings"),
    page("profile/", "dashboard.html", "profile"),
    page("history/", "history.html", "history"),
    page("job/", "job.html", "job"),
    page("stats/", "stats.html", "stats"),
    path("health/", views.health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.jobs.urls")),
    path("api/v1/", include("apps.stats.urls")),
    path("api/v1/", include("apps.scheduling.urls")),
    path("api/v1/", include("apps.evals.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += [
        path("api-auth/", include("rest_framework.urls")),
        path("sentry-debug/", lambda request: 1 / 0),
    ]
