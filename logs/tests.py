from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from contents.models import Content


User = get_user_model()


class AnalysisHistoryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="history-user",
            nickname="historyuser",
            display_name="History User",
            email="history@example.com",
            password="password1234",
        )
        self.client.force_authenticate(user=self.user)

    def test_exact_duplicate_block_uses_reupload_summary(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="block",
            decision="block",
            original_file="",
            original_filename="duplicate.png",
            mime_type="image/png",
            file_size=123,
            reason="동일한 원본 이미지가 이미 처리되었습니다. (기존 콘텐츠 ID: 11111111-1111-1111-1111-111111111111)",
            top_cosine=1.0,
            top_phash_dist=0,
        )

        response = self.client.get("/api/logs/history/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["summary"], "동일한 저작물 재업로드로 차단")

    def test_rejected_review_vote_remains_review_result_in_history(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="block",
            decision="block",
            original_file="",
            original_filename="review-rejected.png",
            mime_type="image/png",
            file_size=123,
            reason="커뮤니티 검증 거절",
            top_cosine=0.81,
            top_phash_dist=6,
            blockchain={
                "mint_kind": "review_vote",
                "vote": {
                    "status": "Rejected",
                    "upvotes": 3,
                    "downvotes": 7,
                    "end_time_display": "2026.04.17 12:00",
                },
            },
        )

        response = self.client.get("/api/logs/history/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["type"], "review")
        self.assertEqual(payload[0]["summary"], "투표 종료 · 반대 우세")
        self.assertIn("찬성 3 · 반대 7", payload[0]["extra"])
