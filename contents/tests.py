from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from analysis.contracts import (
    GuardCandidateV1,
    GuardResponseV1,
    GuardScoresV1,
    GuardTimingV1,
    GuardWatermarkResultV1,
)
from analysis.models import AIJob
from .models import Content


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

    @patch("contents.services.AnalysisGuardService.run_guard_v1")
    def test_register_image_runs_guard_and_persists_result(self, mocked_guard):
        mocked_guard.return_value = GuardResponseV1(
            job_id="job-1",
            mode="register",
            content_type="image",
            success=True,
            decision="allow",
            reason="No strong near-duplicate found",
            next_action="none",
            scores=GuardScoresV1(top_cosine=0.1243, top_phash_dist=28, policy_version="v1"),
            top_match=GuardCandidateV1(
                db_key="db/item.png",
                db_file="item.png",
                cosine=0.1243,
                phash_dist=28,
            ),
            candidates=[],
            watermark=GuardWatermarkResultV1(
                requested=True,
                applied=False,
                model="wam",
                nbits=32,
                scaling_w=2.0,
                proportion_masked=0.65,
            ),
            timing_ms=GuardTimingV1(download=5, embed=10, ann_search=3, phash=1, total=19),
        )

        upload = SimpleUploadedFile(
            "sample.png",
            b"\x89PNG\r\n\x1a\nfakepngcontent",
            content_type="image/png",
        )

        response = self.client.post(
            "/api/contents/register/",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "allow")
        self.assertEqual(Content.objects.count(), 1)

        content = Content.objects.get()
        self.assertEqual(content.owner, self.user)
        self.assertEqual(content.status, "allow")
        self.assertEqual(content.decision, "allow")
        self.assertEqual(content.original_filename, "sample.png")
        self.assertEqual(content.original_file.name, "")
        self.assertIsNotNone(content.analyzed_at)

    def test_register_rejects_non_image_file(self):
        upload = SimpleUploadedFile(
            "sample.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )

        response = self.client.post(
            "/api/contents/register/",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Content.objects.count(), 0)

    def test_register_sanitizes_filename_before_persisting(self):
        upload = SimpleUploadedFile(
            "../../evil file!!.png",
            b"\x89PNG\r\n\x1a\nfakepngcontent",
            content_type="image/png",
        )

        with patch("contents.views.S3StorageService.is_enabled", return_value=True), \
             patch("contents.services.S3StorageService.is_enabled", return_value=True), \
             patch("contents.services.S3StorageService.upload_file"), \
             patch("contents.services.S3StorageService.generate_presigned_get_url", return_value="https://example.com/file.png"), \
             patch("contents.services.S3StorageService.build_s3_uri", return_value="s3://bucket/original/1/test/file.png"), \
             patch("analysis.tasks.run_register_analysis_job.delay") as mocked_delay:
            mocked_delay.return_value.id = "celery-task-1"
            response = self.client.post(
                "/api/contents/register/",
                {"file": upload},
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        content = Content.objects.get()
        self.assertEqual(content.original_filename, "evil file_.png")

    def test_register_rejects_mime_and_extension_mismatch(self):
        upload = SimpleUploadedFile(
            "sample.png",
            b"\xff\xd8\xff\xe0fakejpegcontent",
            content_type="image/jpeg",
        )

        response = self.client.post(
            "/api/contents/register/",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("확장자와 MIME", str(response.json()))

    @patch("contents.views.S3StorageService.is_enabled", return_value=True)
    @patch("contents.services.S3StorageService.is_enabled", return_value=True)
    @patch("contents.services.S3StorageService.upload_file")
    @patch("contents.services.S3StorageService.generate_presigned_get_url", return_value="https://example.com/file.png")
    @patch("contents.services.S3StorageService.build_s3_uri", return_value="s3://bucket/original/1/test/file.png")
    @patch("analysis.tasks.run_register_analysis_job.delay")
    def test_register_blocks_duplicate_source_after_success(
        self,
        mocked_delay,
        *_mocks,
    ):
        mocked_delay.return_value.id = "celery-task-1"

        first_upload = SimpleUploadedFile(
            "sample.png",
            b"\x89PNG\r\n\x1a\nsamecontent",
            content_type="image/png",
        )
        first_response = self.client.post("/api/contents/register/", {"file": first_upload}, format="multipart")

        self.assertEqual(first_response.status_code, 202)
        first_content = Content.objects.get()
        AIJob.objects.filter(content=first_content, job_type="register").update(status="success")

        second_upload = SimpleUploadedFile(
            "sample.png",
            b"\x89PNG\r\n\x1a\nsamecontent",
            content_type="image/png",
        )
        second_response = self.client.post("/api/contents/register/", {"file": second_upload}, format="multipart")

        self.assertEqual(second_response.status_code, 200)
        payload = second_response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["content"]["decision"], "block")
        self.assertEqual(payload["content"]["status"], "block")
        self.assertIn("동일한 원본 이미지", payload["content"]["reason"])
        self.assertEqual(Content.objects.count(), 2)
