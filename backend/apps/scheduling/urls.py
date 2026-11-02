from django.urls import path

from . import views

urlpatterns = [
    path(
        "scheduled-emails/",
        views.ScheduledEmailListCreateView.as_view(),
        name="scheduled-email-list-create",
    ),
    path(
        "scheduled-emails/<uuid:pk>/",
        views.ScheduledEmailUpdateView.as_view(),
        name="scheduled-email-update",
    ),
    path(
        "scheduled-emails/<uuid:pk>/cancel/",
        views.ScheduledEmailCancelView.as_view(),
        name="scheduled-email-cancel",
    ),
]
