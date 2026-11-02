"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from . import views


def trigger_error(request):
    division_by_zero = 1 / 0


urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.login, name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.logout, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("settings/", views.settings, name="settings"),
    path(
        "profile/", views.settings, name="profile"
    ),  # Route legacy profile URL to settings redirect
    path("history/", views.history, name="history"),
    path("job/", views.job, name="job"),
    path("stats/", views.stats, name="stats"),
    path("health/", views.health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.jobs.urls")),
    path("api/v1/", include("apps.stats.urls")),
    path("api/v1/", include("apps.scheduling.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("sentry-debug/", trigger_error),
]

if settings.DEBUG:
    urlpatterns += [path("api-auth/", include("rest_framework.urls"))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
