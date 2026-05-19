from pathlib import Path
from unittest.mock import patch

import fitz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from contents.api.serializers import ContentSerializer
from contents.api.services import ContentRegistrationService
from contents.models import Content
from contents.preview_service import create_pdf_first_page_preview
from contents.verification_service import ContentVerificationService

User = get_user_model()


def write_sample_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=240, height=320)
    page.insert_text((36, 72), "Verimarka PDF Preview")
    document.save(path)
    document.close()


class DocumentPreviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="preview-user",
            nickname="previewuser",
            display_name="Preview User",
            email="preview@example.com",
            password="password1234",
        )

    def test_create_pdf_first_page_preview_stores_local_png(self):
        source_path = Path(settings.MEDIA_ROOT) / "sample-preview-source.pdf"
        write_sample_pdf(source_path)

        preview = create_pdf_first_page_preview(
            source_path=source_path,
            owner_id=self.user.id,
            content_public_id="preview-content",
            filename="sample.pdf",
        )

        self.assertEqual(preview["preview_mime_type"], "image/png")
        self.assertTrue(preview["preview_url"].endswith("/sample_page1.png"))
        self.assertTrue(Path(preview["preview_path"]).exists())

    def test_content_serializer_uses_document_preview_for_file_url(self):
        preview_path = Path(settings.MEDIA_ROOT) / "preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(b"fakepng")
        content = Content.objects.create(
            owner=self.user,
            content_type="document",
            status="verified",
            decision="verified",
            original_file="",
            original_filename="contract.pdf",
            mime_type="application/pdf",
            file_size=123,
            document_metadata={
                "preview": {
                    "preview_url": "/media/preview.png",
                    "preview_path": str(preview_path),
                    "preview_mime_type": "image/png",
                }
            },
        )

        payload = ContentSerializer(content).data

        self.assertEqual(payload["file_url"], "/media/preview.png")

    def test_document_register_result_preserves_existing_preview_metadata(self):
        content = Content.objects.create(
            owner=self.user,
            content_type="document",
            status="pending",
            original_file="",
            original_filename="contract.pdf",
            mime_type="application/pdf",
            file_size=123,
            document_metadata={
                "preview": {
                    "preview_url": "https://cdn.example.com/preview.png",
                    "preview_mime_type": "image/png",
                }
            },
        )

        ContentRegistrationService.apply_document_register_result(
            content=content,
            result={
                "decision": "verified",
                "watermark": {"applied": True, "output_key": "document/out.pdf"},
                "assets": {"original_s3_key": "document/in.pdf"},
            },
        )

        content.refresh_from_db()
        self.assertEqual(
            content.document_metadata["preview"]["preview_url"],
            "https://cdn.example.com/preview.png",
        )

    @patch(
        "contents.verification_service.create_pdf_first_page_preview",
        return_value={
            "preview_key": "document/preview/upload_page1.png",
            "preview_url": "https://cdn.example.com/upload_page1.png",
            "preview_mime_type": "image/png",
        },
    )
    @patch(
        "contents.verification_service.S3StorageService.is_enabled", return_value=True
    )
    @patch("contents.verification_service.S3StorageService.upload_file")
    @patch(
        "contents.verification_service.S3StorageService.generate_presigned_get_url",
        return_value="https://cdn.example.com/upload.pdf",
    )
    @patch(
        "contents.verification_service.S3StorageService.build_s3_uri",
        return_value="s3://bucket/document/verify_request/upload.pdf",
    )
    @patch(
        "contents.verification_service.S3StorageService.build_content_key",
        return_value="document/verify_request/upload.pdf",
    )
    def test_verify_source_input_uses_pdf_preview_url(
        self,
        _mocked_build_key,
        _mocked_build_s3_uri,
        _mocked_generate_url,
        _mocked_upload_file,
        _mocked_storage,
        _mocked_preview,
    ):
        source_path = Path(settings.MEDIA_ROOT) / "verify-preview-source.pdf"
        write_sample_pdf(source_path)
        upload = type(
            "Upload",
            (),
            {
                "name": "upload.pdf",
                "content_type": "application/pdf",
            },
        )()

        source_input = ContentVerificationService._build_source_input(
            temp_path=source_path,
            upload=upload,
            content_type_override="document",
        )

        self.assertEqual(
            source_input["preview_url"], "https://cdn.example.com/upload_page1.png"
        )
