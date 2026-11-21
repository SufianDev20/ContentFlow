from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.jobs.services import llm

from .models import Profile, User

MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024
# Maps each accepted content type to the extension stored for it, so the
# stored extension follows the verified bytes, not the client's filename.
AVATAR_EXTENSIONS = {
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
        fields = ["default_model", "avatar_url"]

    def get_avatar_url(self, obj):
        if not (obj.avatar and hasattr(obj.avatar, "url")):
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileNestedSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "created_at", "profile"]
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=False)
    default_model = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )

    def validate_default_model(self, value):
        if not value:
            return value
        if value not in llm.all_model_ids():
            raise serializers.ValidationError(
                "default_model is not a currently available model."
            )
        return value

    def update_user_and_profile(self, user):
        data = self.validated_data
        if "full_name" in data:
            user.full_name = data["full_name"]
            user.save(update_fields=["full_name"])
        if "default_model" in data:
            user.profile.default_model = data["default_model"]
            user.profile.save()
        return user


class AvatarUploadSerializer(serializers.Serializer):
    """Validates the uploaded bytes' type and size; exposes `verified_extension` on the file."""

    avatar = serializers.ImageField()

    def validate_avatar(self, value):
        if value.content_type not in AVATAR_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported file type. Upload a JPEG, PNG, or WebP image."
            )
        if value.size > MAX_AVATAR_SIZE_BYTES:
            raise serializers.ValidationError("Image must be under 2MB.")
        value.verified_extension = AVATAR_EXTENSIONS[value.content_type]
        return value


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
        return value
