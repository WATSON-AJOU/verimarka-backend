from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from analysis.services import AIIntegrationError
from contents.models import Content
from contents.watermark_service import ContentWatermarkService


User = get_user_model()


class ContentWatermarkServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="watermark-user",
            nickname="watermarkuser",
            display_name="Watermark User",
            email="watermark@example.com",
            password="password1234",
            phone="01077778888",
            phone_verified=True,
        )

    def _create_content(self) -> Content:
        return Content.objects.create(
            owner=self.user,
            content_type="image",
            status="allow",
            decision="allow",
            original_file=SimpleUploadedFile("watermark.png", b"fake-image-bytes", content_type="image/png"),
            original_filename="watermark.png",
            mime_type="image/png",
            file_size=16,
            watermark={},
        )

    @patch("contents.watermark_service.ContentBlockchainService._ensure_vector_upserted")
    @patch("contents.watermark_service.WatermarkAIService.embed", side_effect=RuntimeError("embed exploded"))
    @patch("contents.watermark_service.S3StorageService.is_enabled", return_value=False)
    def test_apply_watermark_resets_processing_on_unexpected_error(self, _mocked_storage, _mocked_embed, _mocked_upsert):
        content = self._create_content()

        with self.assertRaises(AIIntegrationError) as exc:
            ContentWatermarkService.apply_watermark(content=content)

        content.refresh_from_db()
        self.assertEqual(exc.exception.error_code, "WATERMARK_PROCESSING_FAIL")
        self.assertFalse(content.watermark.get("processing"))
        self.assertFalse(content.watermark.get("applied"))
        self.assertEqual(content.watermark.get("last_error"), "embed exploded")
