"""
Authentication and account settings for ContentFlow AI

Endpoints:
  POST   /api/v1/auth/register/        - create account
  POST   /api/v1/auth/login/           - sets httpOnly JWT cookies
  POST   /api/v1/auth/token/refresh/   - rotates access cookie using refresh cookie
  POST   /api/v1/auth/logout/          - blacklists refresh token, clears cookies
  GET    /api/v1/auth/me/              - retrieve current user profile
  GET    /api/v1/auth/profile/         - retrieve settings-modal fields
  PATCH  /api/v1/auth/profile/         - update full_name / theme_color / default_model
  POST   /api/v1/auth/profile/avatar/  - upload profile image
  DELETE /api/v1/auth/profile/avatar/  - remove profile image
  DELETE /api/v1/auth/account/         - hard delete account (requires password)
"""

import uuid as _uuid
from cloudinary import uploader as cloudinary_uploader
from django.conf import settings
from rest_framework import permissions, status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from .models import User, Profile
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    ProfileUpdateSerializer,
    AvatarUploadSerializer,
    AccountDeleteSerializer,
)


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class AccountActionThrottle(UserRateThrottle):
    scope = "account_action"


def _set_jwt_cookies(response, access, refresh=None):
    """Shared cookie-setting logic for login and refresh."""
    cfg = settings.SIMPLE_JWT
    response.set_cookie(
        cfg["AUTH_COOKIE"],
        access,
        max_age=int(cfg["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=cfg["AUTH_COOKIE_HTTP_ONLY"],
        secure=cfg["AUTH_COOKIE_SECURE"],
        samesite=cfg["AUTH_COOKIE_SAMESITE"],
        path="/",
    )
    if refresh is not None:
        response.set_cookie(
            cfg["AUTH_COOKIE_REFRESH"],
            refresh,
            max_age=int(cfg["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            httponly=cfg["AUTH_COOKIE_HTTP_ONLY"],
            secure=cfg["AUTH_COOKIE_SECURE"],
            samesite=cfg["AUTH_COOKIE_SAMESITE"],
            path="/api/v1/auth/",
        )


def _delete_cloudinary_resource(resource):
    """Delete a Cloudinary asset referenced by a CloudinaryField value."""
    public_id = getattr(resource, "public_id", None)
    if not public_id:
        return

    cloudinary_uploader.destroy(
        public_id,
        invalidate=True,
        resource_type=getattr(resource, "resource_type", "image"),
        type=getattr(resource, "type", "upload"),
    )


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access = serializer.validated_data["access"]
        refresh = serializer.validated_data["refresh"]

        user = serializer.user
        body = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "default_model": getattr(user.profile, "default_model", ""),
        }
        response = Response(body, status=status.HTTP_200_OK)
        _set_jwt_cookies(response, str(access), str(refresh))
        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if refresh_cookie is None:
            return Response(
                {"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = self.get_serializer(data={"refresh": refresh_cookie})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            return Response(
                {"detail": "Refresh token invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        access = serializer.validated_data["access"]
        new_refresh = serializer.validated_data.get("refresh")
        response = Response({"detail": "Refreshed."}, status=status.HTTP_200_OK)
        _set_jwt_cookies(response, access, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if refresh_cookie:
            try:
                RefreshToken(refresh_cookie).blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.SIMPLE_JWT["AUTH_COOKIE"], path="/")
        response.delete_cookie(
            settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"], path="/api/v1/auth/"
        )
        return response


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = User.objects.select_related("profile").get(pk=request.user.pk)
        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        if self.request.method in ["PATCH", "POST", "DELETE"]:
            return [AccountActionThrottle()]
        return []

    def get(self, request):
        user = User.objects.select_related("profile").get(pk=request.user.pk)
        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update_user_and_profile(request.user)

        user = User.objects.select_related("profile").get(pk=request.user.pk)
        response_serializer = UserSerializer(user, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class AvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AccountActionThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        previous_avatar = profile.avatar

        uploaded = serializer.validated_data["avatar"]
        ext = getattr(uploaded, "verified_extension", None)
        if ext:
            uploaded.name = f"{_uuid.uuid4().hex}.{ext}"
        profile.avatar = uploaded
        profile.save()
        if previous_avatar:
            _delete_cloudinary_resource(previous_avatar)

        user = User.objects.select_related("profile").get(pk=request.user.pk)
        response_serializer = UserSerializer(user, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        profile = getattr(request.user, "profile", None)
        if profile and profile.avatar:
            _delete_cloudinary_resource(profile.avatar)
            profile.avatar = None
            profile.save()

        user = User.objects.select_related("profile").get(pk=request.user.pk)
        response_serializer = UserSerializer(user, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class AccountDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AccountActionThrottle]

    def delete(self, request):
        serializer = AccountDeleteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        profile = getattr(user, "profile", None)
        if profile and profile.avatar:
            _delete_cloudinary_resource(profile.avatar)

        user.delete()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.SIMPLE_JWT["AUTH_COOKIE"], path="/")
        response.delete_cookie(
            settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"], path="/api/v1/auth/"
        )
        return response
