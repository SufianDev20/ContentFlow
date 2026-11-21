import logging
import uuid

import cloudinary.exceptions
from cloudinary import uploader as cloudinary_uploader
from django.conf import settings
from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .serializers import (
    AccountDeleteSerializer,
    AvatarUploadSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttles import AccountActionThrottle, AuthRateThrottle

logger = logging.getLogger(__name__)

# The refresh cookie is only sent to the auth endpoints.
REFRESH_COOKIE_PATH = "/api/v1/auth/"


def _set_jwt_cookies(response, access, refresh=None):
    cfg = settings.SIMPLE_JWT
    cookie_options = {
        "httponly": cfg["AUTH_COOKIE_HTTP_ONLY"],
        "secure": cfg["AUTH_COOKIE_SECURE"],
        "samesite": cfg["AUTH_COOKIE_SAMESITE"],
    }
    response.set_cookie(
        cfg["AUTH_COOKIE"],
        access,
        max_age=int(cfg["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        path="/",
        **cookie_options,
    )
    if refresh is not None:
        response.set_cookie(
            cfg["AUTH_COOKIE_REFRESH"],
            refresh,
            max_age=int(cfg["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            path=REFRESH_COOKIE_PATH,
            **cookie_options,
        )


def _clear_jwt_cookies(response):
    response.delete_cookie(settings.SIMPLE_JWT["AUTH_COOKIE"], path="/")
    response.delete_cookie(
        settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"], path=REFRESH_COOKIE_PATH
    )


def _user_response(request):
    user = User.objects.select_related("profile").get(pk=request.user.pk)
    return Response(UserSerializer(user, context={"request": request}).data)


def _delete_cloudinary_resource(resource):
    """Delete a Cloudinary asset; returns False (and logs) if Cloudinary errors."""
    public_id = getattr(resource, "public_id", None)
    if not public_id:
        return True

    try:
        cloudinary_uploader.destroy(
            public_id,
            invalidate=True,
            resource_type=getattr(resource, "resource_type", "image"),
            type=getattr(resource, "type", "upload"),
        )
    except cloudinary.exceptions.Error:
        logger.warning("Cloudinary delete failed for %s", public_id, exc_info=True)
        return False
    return True


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

        user = serializer.user
        response = Response(
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "default_model": user.profile.default_model,
            }
        )
        _set_jwt_cookies(
            response,
            str(serializer.validated_data["access"]),
            str(serializer.validated_data["refresh"]),
        )
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

        response = Response({"detail": "Refreshed."})
        _set_jwt_cookies(
            response,
            serializer.validated_data["access"],
            serializer.validated_data.get("refresh"),
        )
        return response


class LogoutView(APIView):
    # Open to expired sessions too, so logging out always clears the refresh cookie.
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if refresh_cookie:
            try:
                RefreshToken(refresh_cookie).blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_jwt_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return _user_response(request)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AccountActionThrottle]

    def get(self, request):
        return _user_response(request)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update_user_and_profile(request.user)
        return _user_response(request)


class AvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AccountActionThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = request.user.profile
        previous_avatar = profile.avatar

        uploaded = serializer.validated_data["avatar"]
        uploaded.name = f"{uuid.uuid4().hex}.{uploaded.verified_extension}"
        profile.avatar = uploaded
        try:
            with transaction.atomic():
                profile.save()
        except cloudinary.exceptions.Error:
            logger.exception("Cloudinary avatar upload failed")
            return Response(
                {"detail": "Avatar upload failed. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if previous_avatar:
            _delete_cloudinary_resource(previous_avatar)

        return _user_response(request)

    def delete(self, request):
        profile = request.user.profile
        if profile.avatar:
            _delete_cloudinary_resource(profile.avatar)
            profile.avatar = None
            profile.save()
        return _user_response(request)


class AccountDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AccountActionThrottle]

    def delete(self, request):
        serializer = AccountDeleteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        if user.profile.avatar:
            _delete_cloudinary_resource(user.profile.avatar)

        user.delete()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_jwt_cookies(response)
        return response
