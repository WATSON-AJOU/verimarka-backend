from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from analysis.contracts import GuardResponseV1, GuardScoresV1, GuardTimingV1, GuardWatermarkResultV1
from logs.models import VerificationHistoryLog
from contents.verification_service import ContentVerificationService


User = get_user_model()


class ContentVerifyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verifier",
            nickname="verifier",
            display_name="Verifier",
            email="verifier@example.com",
            password="password1234",
            phone="01033334444",
            phone_verified=True,
        )

    @patch("contents.verification_service.S3StorageService.is_enabled", return_value=False)
    @patch("contents.verification_service.AnalysisGuardService.run_guard_v1")
    @patch("contents.verification_service.WatermarkAIService.detect")
    def test_verify_result_preserves_display_filename(self, mocked_detect, mocked_guard, _mocked_storage):
        mocked_detect.return_value = {
            "success": True,
            "result": {"detected": False, "payload_id": None, "confidence": 0.0, "bit_accuracy": 0.0},
        }
        mocked_guard.return_value = GuardResponseV1(
            job_id="job-verify-1",
            mode="register",
            content_type="image",
            success=True,
            decision="allow",
            reason="No strong near-duplicate found",
            next_action="none",
            scores=GuardScoresV1(top_cosine=0.12, top_phash_dist=28, policy_version="v1"),
            top_match=None,
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

        upload = SimpleUploadedFile("../../verify file!!.png", b"\x89PNG\r\n\x1a\nverifycontent", content_type="image/png")
        payload = ContentVerificationService.verify_image(user=self.user, upload=upload)

        VerificationHistoryLog.objects.create(
            user=self.user,
            outcome=payload.get("outcome", "candidate"),
            uploaded_file_name=(payload.get("uploaded") or {}).get("file_name"),
            uploaded_file_size=(payload.get("uploaded") or {}).get("file_size") or 0,
            uploaded_preview_url=(payload.get("uploaded") or {}).get("preview_url"),
            detect=payload.get("detect") or {},
            blockchain=payload.get("blockchain") or {},
            candidate=payload.get("candidate") or {},
            summary="검증 테스트",
        )

        log = VerificationHistoryLog.objects.get()
        self.assertEqual((payload.get("uploaded") or {}).get("file_name"), "verify file!!.png")
        self.assertEqual(log.uploaded_file_name, "verify file!!.png")
