import uuid
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserManager(BaseUserManager):
    """Custom manager for the custom User model where email is the unique identifier."""

    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, full_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model using email as the primary login identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    # Required for Django admin access flags
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Link our custom manager
    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    def __str__(self):
        return self.email


def avatar_upload_path(instance, filename):
    """
    Generate a randomized storage path for avatar uploads.

    Never uses the original filename. Only the extension is kept, and only
    after validation against ALLOWED_AVATAR_EXTENSIONS in the serializer.
    Path is namespaced by user id so one user can never overwrite another
    user's file by guessing a path.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"avatars/{instance.user_id}/{uuid.uuid4().hex}.{ext}"


class Profile(models.Model):
    """
    Mutable user preferences and profile data, separate from the auth-focused
    User model. One-to-one with User, created automatically on user creation
    via the post_save signal below.

    default_model is intentionally a plain CharField, not a choices= enum.
    The authoritative list of available models is served at runtime by a
    different app (GET /api/v1/models/available/) and can change without a
    migration. Validation against that live list happens in the serializer,
    not at the database layer.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="profile"
    )
    avatar = models.ImageField(upload_to=avatar_upload_path, blank=True, null=True)
    theme_color = models.CharField(
        max_length=7,
        default="#8A2BE2",
        help_text="Hex color, e.g. #8A2BE2. Validated in serializer.",
    )
    default_model = models.CharField(max_length=100, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile<{self.user.email}>"


@receiver(post_save, sender=User)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    """Ensure every User row has exactly one Profile row, created atomically
    at user-creation time so no code path ever has to null-check user.profile."""
    if created:
        Profile.objects.get_or_create(user=instance)
