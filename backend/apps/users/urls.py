from django.urls import path
from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path(
        "auth/token/refresh/",
        views.CookieTokenRefreshView.as_view(),  # CHANGED from TokenRefreshView
        name="auth-token-refresh",
    ),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),  # NEW
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/profile/", views.ProfileView.as_view(), name="auth-profile"),
    path(
        "auth/profile/avatar/", views.AvatarView.as_view(), name="auth-profile-avatar"
    ),
    path(
        "auth/account/", views.AccountDeleteView.as_view(), name="auth-account-delete"
    ),
]
