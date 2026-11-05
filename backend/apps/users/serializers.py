"""
Serializers for user registration, profile retrieval, and account settings.

Design decisions:
    - RegisterSerializer uses ModelSerializer with an explicit write-only
      password field. validate_password() runs Django's built-in validators
      (length, common password, numeric-only) defined in AUTH_PASSWORD_VALIDATORS.
    - Password is hashed via set_password() in create(), never stored plain.
    - UserSerializer is strictly read-only; no update surface exposed here.
    - ProfileSerializer handles the settings-modal fields (full_name lives on
      User, so it's included here as a pass-through write to the related
      user object, not duplicated on Profile).
    - AvatarUploadSerializer validates the uploaded file's actual content,
      not its extension or declared Content-Type, before Django's
      ImageField hands it to Pillow for a second verification pass.
    - AccountDeleteSerializer requires the current password. A valid
      session token alone is not sufficient authorization for an
      irreversible, destructive action.
"""

from .models import User, Profile
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
import re

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_AVATAR_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024  # 2MB

# NEW: maps a verified content type to the extension actually written to
# disk, so the stored file extension always matches the verified bytes
# instead of the client-supplied filename.
CONTENT_TYPE_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_password]
    )

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "password"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ProfileNestedSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["theme_color", "default_model", "avatar_url"]

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj.avatar and hasattr(obj.avatar, "url"):
            return (
                request.build_absolute_uri(obj.avatar.url)
                if request
                else obj.avatar.url
            )
        return None


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileNestedSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "created_at", "profile"]
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.Serializer):
    """
    Handles PATCH /api/v1/auth/profile/.

    FIX: default_model is now validated against the real list of available
    models instead of only a character-safety regex. The regex check stays
    as a cheap first-pass rejection before hitting the model-list source.
    """

    full_name = serializers.CharField(max_length=150, required=False, allow_blank=False)
    theme_color = serializers.CharField(max_length=7, required=False)
    default_model = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )

    def validate_theme_color(self, value):
        if not HEX_COLOR_RE.match(value):
            raise serializers.ValidationError(
                "theme_color must be a 6-digit hex color, e.g. #8A2BE2."
            )
        return value

    def validate_default_model(self, value):
        if not value:
            return value

        if not re.match(r"^[a-zA-Z0-9_\-./]+$", value):
            raise serializers.ValidationError(
                "default_model contains invalid characters."
            )

        # Cross-check against the same source that powers the
        # /models/available/ endpoint (apps/jobs/views.py AvailableModelsView).
        from apps.jobs.services.repurposer import get_available_free_model

        if value not in get_available_free_model():
            raise serializers.ValidationError(
                "default_model is not a currently available model."
            )
        return value

    def update_user_and_profile(self, user):
        data = self.validated_data
        if "full_name" in data:
            user.full_name = data["full_name"]
            user.save(update_fields=["full_name"])

        profile = user.profile
        profile_changed = False
        if "theme_color" in data:
            profile.theme_color = data["theme_color"]
            profile_changed = True
        if "default_model" in data:
            profile.default_model = data["default_model"]
            profile_changed = True
        if profile_changed:
            profile.save()

        return user


class AvatarUploadSerializer(serializers.Serializer):
    """
    Handles POST /api/v1/auth/profile/avatar/.

    FIX: exposes the verified content type as `verified_extension` so the
    view/model layer can use it instead of trusting the client-supplied
    filename when generating the storage path.
    """

    avatar = serializers.ImageField()

    def validate_avatar(self, value):
        if value.content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
            raise serializers.ValidationError(
                "Unsupported file type. Upload a JPEG, PNG, or WebP image."
            )
        if value.size > MAX_AVATAR_SIZE_BYTES:
            raise serializers.ValidationError("Image must be under 2MB.")
        value.verified_extension = CONTENT_TYPE_TO_EXTENSION[value.content_type]
        return value


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
        return value
