from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .contracts import (
    GuardCandidateV1,
    GuardResponseV1,
    GuardScoresV1,
    GuardTimingV1,
    GuardWatermarkResultV1,
)
from .services import AIIntegrationError


User = get_user_model()


class GuardAnalyzeViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="tester",
            nickname="tester",
            display_name="Tester",
            email="tester@example.com",
            password="password1234",
            phone="01012345678",
            phone_verified=True,
        )
        self.client.force_authenticate(user=self.user)

    @patch("analysis.views.AnalysisGuardService.run_guard_v1")
    def test_guard_endpoint_returns_success_payload(self, mocked_run_guard):
        mocked_run_guard.return_value = GuardResponseV1(
            job_id="job-1",
            mode="register",
            content_type="image",
            success=True,
            decision="allow",
            reason="No similar images found in database",
            next_action="none",
            scores=GuardScoresV1(
                top_cosine=0.12,
                top_phash_dist=24,
                policy_version="v1",
            ),
            top_match=GuardCandidateV1(
                db_key="db/item.png",
                db_file="item.png",
                cosine=0.12,
                phash_dist=24,
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
            timing_ms=GuardTimingV1(download=10, total=30),
        )

        response = self.client.post(
            "/api/analysis/guard/",
            {
                "job_id": "job-1",
                "mode": "register",
                "content_type": "image",
                "input": [
                    {
                        "url": "file:///tmp/sample.png",
                        "filename": "sample.png",
                        "mime_type": "image/png",
                    }
                ],
                "meta": {"user_id": "u1", "content_id": "c1"},
                "options": {
                    "search": {"top_k": 10, "top_phash": 10},
                    "watermark": {
                        "apply_on_allow": True,
                        "model": "wam",
                        "nbits": 32,
                        "scaling_w": 2.0,
                        "proportion_masked": 0.65,
                    },
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "allow")
        self.assertEqual(response.json()["next_action"], "none")

    def test_guard_endpoint_requires_valid_payload(self):
        response = self.client.post(
            "/api/analysis/guard/",
            {
                "job_id": "job-2",
                "mode": "register",
                "content_type": "image",
                "input": [],
                "meta": {"user_id": "u1", "content_id": "c1"},
                "options": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "INVALID_INPUT")

    @patch("analysis.views.AnalysisGuardService.run_guard_v1")
    def test_guard_endpoint_formats_ai_integration_error(self, mocked_run_guard):
        mocked_run_guard.side_effect = AIIntegrationError(
            error_code="AI_TIMEOUT",
            error_message="AI 처리 시간이 초과되었습니다.",
            retryable=True,
            status_code=503,
            job_id="job-timeout",
        )

        response = self.client.post(
            "/api/analysis/guard/",
            {
                "job_id": "job-timeout",
                "mode": "register",
                "content_type": "image",
                "input": [{"url": "file:///tmp/sample.png"}],
                "meta": {"user_id": "u1", "content_id": "c1"},
                "options": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "AI_TIMEOUT")
        self.assertEqual(response.json()["detail"], "AI 처리 시간이 초과되었습니다.")
        self.assertTrue(response.json()["retryable"])

    @patch("analysis.views.AnalysisGuardService.run_guard_v1")
    def test_guard_endpoint_formats_unhandled_exception_as_json(self, mocked_run_guard):
        mocked_run_guard.side_effect = RuntimeError("unexpected boom")

        response = self.client.post(
            "/api/analysis/guard/",
            {
                "job_id": "job-crash",
                "mode": "register",
                "content_type": "image",
                "input": [{"url": "file:///tmp/sample.png"}],
                "meta": {"user_id": "u1", "content_id": "c1"},
                "options": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error_code"], "INTERNAL_SERVER_ERROR")
        self.assertEqual(response.json()["detail"], "서버 내부 오류가 발생했습니다.")
