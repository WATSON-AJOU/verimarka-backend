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
                proportion_masked=0.35,
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
        self.assertTrue(content.original_file.name.endswith("sample.png"))
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
