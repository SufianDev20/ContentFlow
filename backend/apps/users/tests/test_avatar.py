"""
apps/users/tests/test_avatar.py

Avatar upload/delete must degrade gracefully when Cloudinary rejects a request.
Cloudinary calls are patched; no network access.
"""

import io
from unittest import mock

import cloudinary.exceptions
from cloudinary import CloudinaryResource
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User


def _png_upload():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return SimpleUploadedFile("a.png", buf.getvalue(), content_type="image/png")


def _resource(public_id):
    return CloudinaryResource(
        public_id=public_id,
        format="png",
        version="1",
        type="upload",
        resource_type="image",
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class AvatarCloudinaryErrorTests(APITestCase):
    def setUp(self):
        self.url = reverse("auth-profile-avatar")
        self.user = User.objects.create_user(
            email="jane@example.com", password="StrongPass123!", full_name="Jane"
        )
        self.client.force_authenticate(user=self.user)
        self.enterContext(
            mock.patch.object(cloudinary.config(), "cloud_name", "test-cloud")
        )

    def _set_existing_avatar(self):
        profile = self.user.profile
        profile.avatar = _resource("avatars/old")
        profile.save()

    def test_avatar_upload_cloudinary_auth_error_returns_502(self):
        with mock.patch(
            "cloudinary.uploader.upload_resource",
            side_effect=cloudinary.exceptions.AuthorizationRequired(
                "Invalid Signature"
            ),
        ):
            response = self.client.post(
                self.url, {"avatar": _png_upload()}, format="multipart"
            )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("detail", response.data)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)

    def test_avatar_upload_old_avatar_delete_failure_still_succeeds(self):
        self._set_existing_avatar()
        with mock.patch(
            "cloudinary.uploader.upload_resource",
            return_value=_resource("avatars/new"),
        ), mock.patch(
            "cloudinary.uploader.destroy",
            side_effect=cloudinary.exceptions.Error("boom"),
        ):
            response = self.client.post(
                self.url, {"avatar": _png_upload()}, format="multipart"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.avatar.public_id, "avatars/new")

    def test_avatar_delete_cloudinary_error_still_clears_avatar(self):
        self._set_existing_avatar()
        with mock.patch(
            "cloudinary.uploader.destroy",
            side_effect=cloudinary.exceptions.AuthorizationRequired(
                "Invalid Signature"
            ),
        ):
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)
