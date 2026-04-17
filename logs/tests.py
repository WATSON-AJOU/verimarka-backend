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

    def test_approved_review_vote_returns_review_and_allow_history_items(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="allow",
            decision="allow",
            original_file="",
            original_filename="review-approved.png",
            mime_type="image/png",
            file_size=123,
            reason="커뮤니티 검증 승인",
            top_cosine=0.79,
            top_phash_dist=7,
            blockchain={
                "mint_kind": "review_vote",
                "vote": {
                    "status": "Approved",
                    "upvotes": 8,
                    "downvotes": 2,
                    "end_time_display": "2026.04.17 12:00",
                },
            },
        )

        response = self.client.get("/api/logs/history/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual({item["type"] for item in payload}, {"review", "allow"})
        review_item = next(item for item in payload if item["type"] == "review")
        allow_item = next(item for item in payload if item["type"] == "allow")
        self.assertEqual(review_item["summary"], "투표 종료 · 찬성 우세")
        self.assertIn("찬성 8 · 반대 2", review_item["extra"])
        self.assertEqual(allow_item["summary"], "등록 승인 완료")

    def test_approved_review_vote_without_watermark_does_not_look_minted(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="allow",
            decision="allow",
            original_file="",
            original_filename="review-approved-not-minted.png",
            mime_type="image/png",
            file_size=123,
            reason="커뮤니티 검증 승인",
            top_cosine=0.79,
            top_phash_dist=7,
            blockchain={
                "minted": True,
                "mint_kind": "review_vote",
                "network_name": "Sepolia",
                "token_id": 77,
                "vote": {
                    "status": "Approved",
                    "upvotes": 8,
                    "downvotes": 2,
                    "end_time_display": "2026.04.17 12:00",
                },
            },
            watermark={"applied": False},
        )

        response = self.client.get("/api/logs/history/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        allow_item = next(item for item in payload if item["type"] == "allow")
        self.assertEqual(allow_item["summary"], "등록 승인 완료")
        self.assertEqual(allow_item["extra"], "등록 승인됨")
        self.assertIsNone(allow_item["download_url"])

    def test_content_mint_after_review_approval_keeps_review_result_history(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="allow",
            decision="allow",
            original_file="",
            original_filename="review-approved-minted.png",
            mime_type="image/png",
            file_size=123,
            reason="커뮤니티 검증 승인",
            top_cosine=0.79,
            top_phash_dist=7,
            blockchain={
                "minted": True,
                "mint_kind": "content",
                "network_name": "Sepolia",
                "token_id": 88,
                "tx_hash": "0x1234567890abcdef",
                "vote": {
                    "status": "Approved",
                    "upvotes": 8,
                    "downvotes": 2,
                    "end_time_display": "2026.04.17 12:00",
                },
            },
            watermark={"applied": True, "output_url": "/media/watermarked.png"},
        )

        response = self.client.get("/api/logs/history/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual({item["type"] for item in payload}, {"review", "allow"})
        review_item = next(item for item in payload if item["type"] == "review")
        allow_item = next(item for item in payload if item["type"] == "allow")
        self.assertEqual(review_item["summary"], "투표 종료 · 찬성 우세")
        self.assertEqual(allow_item["summary"], "워터마크 & 토큰 발급 완료 (토큰 #88)")
