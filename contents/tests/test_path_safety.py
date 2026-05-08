from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from analysis.api.services import AIIntegrationError
from contents.blockchain_service import ContentBlockchainService
from contents.models import Content
from contents.path_safety import resolve_media_path

User = get_user_model()


class MediaPathSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="path-user",
            nickname="pathuser",
            display_name="Path User",
            email="path@example.com",
            password="password1234",
            phone="01099998888",
            phone_verified=True,
        )

    def _create_content(self, watermark: dict) -> Content:
        return Content.objects.create(
            owner=self.user,
            content_type="image",
            status="allow",
            decision="allow",
            original_file=SimpleUploadedFile(
                "safe.png", b"\x89PNG\r\n\x1a\nsafe", content_type="image/png"
            ),
            original_filename="safe.png",
            mime_type="image/png",
            file_size=16,
            watermark=watermark,
        )

    def test_resolve_media_path_rejects_traversal(self):
        self.assertIsNone(resolve_media_path(f"{settings.MEDIA_URL}../../secret.txt"))

    def test_download_rejects_output_url_outside_media_root(self):
        content = self._create_content(
            {"applied": True, "output_url": f"{settings.MEDIA_URL}../../secret.txt"}
        )
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(
            reverse(
                "content_watermark_download", kwargs={"public_id": content.public_id}
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_load_watermarked_bytes_rejects_output_path_outside_media_root(self):
        content = self._create_content({"applied": True, "output_path": "/etc/passwd"})
        content.original_file = ""
        content.save(update_fields=["original_file"])

        with self.assertRaises(AIIntegrationError):
            ContentBlockchainService._load_watermarked_bytes(content)
