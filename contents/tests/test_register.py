from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from analysis.models import AIJob
from contents.models import Content

User = get_user_model()


class ContentRegisterViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="creator",
            nickname="creator",
            display_name="Creator",
            email="creator@example.com",
            password="password1234",
            phone="01011112222",
            phone_verified=True,
        )
        self.client.force_authenticate(user=self.user)

    @patch("contents.api.views.S3StorageService.is_enabled", return_value=True)
    @patch(
        "contents.api.services.registration.S3StorageService.is_enabled",
        return_value=True,
    )
    @patch("contents.api.services.registration.S3StorageService.upload_file")
    @patch(
        "contents.api.services.registration.S3StorageService.generate_presigned_get_url",
        return_value="https://example.com/file.png",
    )
    @patch(
        "contents.api.services.registration.S3StorageService.build_s3_uri",
        return_value="s3://bucket/original/1/test/file.png",
    )
    @patch("analysis.tasks.run_register_analysis_job.delay")
    def test_register_image_enqueues_async_job(self, mocked_delay, *_mocks):
        mocked_delay.return_value.id = "celery-task-1"
        upload = SimpleUploadedFile(
            "sample.png",
            b"\x89PNG\r\n\x1a\nfakepngcontent",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("content_register"), {"file": upload}, format="multipart"
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        content = Content.objects.get()
        self.assertEqual(content.content_type, "image")
        self.assertEqual(content.original_filename, "sample.png")
        self.assertTrue(
            AIJob.objects.filter(content=content, job_type="register").exists()
        )

    def test_register_rejects_unsupported_file(self):
        upload = SimpleUploadedFile(
            "sample.txt", b"plain text", content_type="text/plain"
        )

        response = self.client.post(
            reverse("content_register"), {"file": upload}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Content.objects.count(), 0)

    @patch("contents.api.views.S3StorageService.is_enabled", return_value=True)
    @patch(
        "contents.api.services.registration.S3StorageService.is_enabled",
        return_value=True,
    )
    @patch("contents.api.services.registration.S3StorageService.upload_file")
    @patch(
        "contents.api.services.registration.S3StorageService.generate_presigned_get_url",
        return_value="https://example.com/file.pdf",
    )
    @patch(
        "contents.api.services.registration.S3StorageService.build_s3_uri",
        return_value="s3://bucket/document/register_request/1/test/file.pdf",
    )
    @patch("analysis.tasks.run_register_analysis_job.delay")
    def test_register_accepts_document_file(self, mocked_delay, *_mocks):
        mocked_delay.return_value.id = "celery-task-doc-1"
        upload = SimpleUploadedFile(
            "sample.pdf", b"%PDF-1.4", content_type="application/pdf"
        )

        response = self.client.post(
            reverse("content_register"), {"file": upload}, format="multipart"
        )

        self.assertEqual(response.status_code, 202)
        content = Content.objects.get()
        self.assertEqual(content.content_type, "document")
        self.assertEqual(content.mime_type, "application/pdf")

    @patch("contents.api.views.S3StorageService.is_enabled", return_value=True)
    @patch(
        "contents.api.services.registration.S3StorageService.is_enabled",
        return_value=True,
    )
    @patch("contents.api.services.registration.S3StorageService.upload_file")
    @patch(
        "contents.api.services.registration.S3StorageService.generate_presigned_get_url",
        return_value="https://example.com/file.docx",
    )
    @patch(
        "contents.api.services.registration.S3StorageService.build_s3_uri",
        return_value="s3://bucket/document/register_request/1/test/file.docx",
    )
    @patch("analysis.tasks.run_register_analysis_job.delay")
    def test_register_accepts_docx_with_generic_mime_type(self, mocked_delay, *_mocks):
        mocked_delay.return_value.id = "celery-task-docx-1"
        upload = SimpleUploadedFile(
            "sample.docx", b"PK\x03\x04docx", content_type="application/octet-stream"
        )

        response = self.client.post(
            reverse("content_register"), {"file": upload}, format="multipart"
        )

        self.assertEqual(response.status_code, 202)
        content = Content.objects.get()
        job = AIJob.objects.get()
        self.assertEqual(content.content_type, "document")
        self.assertEqual(
            content.mime_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(job.request_payload["content_type"], "document")

    @patch("contents.api.views.S3StorageService.is_enabled", return_value=True)
    @patch(
        "contents.api.services.registration.S3StorageService.is_enabled",
        return_value=True,
    )
    @patch("contents.api.services.registration.S3StorageService.upload_file")
    @patch(
        "contents.api.services.registration.S3StorageService.generate_presigned_get_url",
        return_value="https://example.com/file.png",
    )
    @patch(
        "contents.api.services.registration.S3StorageService.build_s3_uri",
        return_value="s3://bucket/original/1/test/file.png",
    )
    @patch("analysis.tasks.run_register_analysis_job.delay")
    def test_register_sanitizes_filename_before_persisting(self, mocked_delay, *_mocks):
        mocked_delay.return_value.id = "celery-task-1"
        upload = SimpleUploadedFile(
            "../../evil file!!.png",
            b"\x89PNG\r\n\x1a\nfakepngcontent",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("content_register"), {"file": upload}, format="multipart"
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(Content.objects.get().original_filename, "evil file!!.png")

    def test_register_rejects_mime_and_extension_mismatch(self):
        upload = SimpleUploadedFile(
            "sample.png", b"\xff\xd8\xff\xe0fakejpegcontent", content_type="image/jpeg"
        )

        response = self.client.post(
            reverse("content_register"), {"file": upload}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("확장자와 MIME", str(response.json()))

    @patch("contents.api.views.S3StorageService.is_enabled", return_value=True)
    @patch(
        "contents.api.services.registration.S3StorageService.is_enabled",
        return_value=True,
    )
    @patch("contents.api.services.registration.S3StorageService.upload_file")
    @patch(
        "contents.api.services.registration.S3StorageService.generate_presigned_get_url",
        return_value="https://example.com/file.png",
    )
    @patch(
        "contents.api.services.registration.S3StorageService.build_s3_uri",
        return_value="s3://bucket/original/1/test/file.png",
    )
    @patch("analysis.tasks.run_register_analysis_job.delay")
    def test_register_blocks_duplicate_source_after_success(
        self, mocked_delay, *_mocks
    ):
        mocked_delay.return_value.id = "celery-task-1"
        first_upload = SimpleUploadedFile(
            "sample.png", b"\x89PNG\r\n\x1a\nsamecontent", content_type="image/png"
        )
        first_response = self.client.post(
            reverse("content_register"), {"file": first_upload}, format="multipart"
        )

        self.assertEqual(first_response.status_code, 202)
        first_content = Content.objects.get()
        AIJob.objects.filter(content=first_content, job_type="register").update(
            status="success"
        )

        second_upload = SimpleUploadedFile(
            "sample.png", b"\x89PNG\r\n\x1a\nsamecontent", content_type="image/png"
        )
        second_response = self.client.post(
            reverse("content_register"), {"file": second_upload}, format="multipart"
        )

        self.assertEqual(second_response.status_code, 200)
        payload = second_response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["content"]["decision"], "block")
        self.assertEqual(payload["content"]["status"], "block")
        self.assertEqual(Content.objects.count(), 2)
