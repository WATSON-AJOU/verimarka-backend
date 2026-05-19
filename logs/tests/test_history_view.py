from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["summary"], "동일한 저작물 재업로드로 차단")

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

        response = self.client.get(reverse("analysis_history"))

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

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual({item["type"] for item in payload}, {"review", "allow"})

    def test_pending_review_vote_after_deadline_uses_confirmation_waiting_summary(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="review",
            decision="review",
            original_file="",
            original_filename="review-expired.png",
            mime_type="image/png",
            file_size=123,
            reason="커뮤니티 검증 진행 중",
            top_cosine=0.79,
            top_phash_dist=7,
            blockchain={
                "mint_kind": "review_vote",
                "vote": {
                    "status": "Pending",
                    "upvotes": 0,
                    "downvotes": 0,
                    "end_time": (timezone.now() - timedelta(hours=1)).isoformat(),
                },
            },
        )

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["type"], "review")
        self.assertEqual(payload[0]["summary"], "투표 마감 및 확인 대기")

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

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        allow_item = next(item for item in response.json() if item["type"] == "allow")
        self.assertEqual(allow_item["summary"], "등록 승인 완료")
        self.assertIsNone(allow_item["download_url"])

    def test_verified_document_history_is_success_not_blocked(self):
        Content.objects.create(
            owner=self.user,
            content_type="document",
            status="verified",
            decision="verified",
            original_file="",
            original_filename="contract.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=123,
            reason="document watermarked and OCR summary extracted",
            watermark={
                "applied": True,
                "output_key": "document/watermarked/contract.pdf",
            },
            blockchain={
                "minted": True,
                "mint_kind": "content",
                "network_name": "Sepolia",
                "token_id": 6,
            },
        )

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()[0]
        self.assertEqual(payload["type"], "verified")
        self.assertEqual(payload["summary"], "워터마크 & 토큰 발급 완료 (토큰 #6)")
        self.assertEqual(payload["extra"], "Sepolia · Token #6")
        self.assertNotEqual(payload["summary"], "등록 차단")

    def test_failed_document_history_is_block_type(self):
        Content.objects.create(
            owner=self.user,
            content_type="document",
            status="failed",
            decision="failed",
            original_file="",
            original_filename="broken-contract.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=123,
            reason="문서 등록 처리에 실패했습니다.",
        )

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()[0]
        self.assertEqual(payload["type"], "block")
        self.assertEqual(payload["summary"], "등록 차단")

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

        response = self.client.get(reverse("analysis_history"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)

    def test_history_page_size_limits_merged_payload(self):
        base_time = timezone.now()
        contents = [
            Content.objects.create(
                owner=self.user,
                content_type="image",
                status="allow",
                decision="allow",
                original_file="",
                original_filename=f"history-{index}.png",
                mime_type="image/png",
                file_size=123,
                reason="등록 승인",
            )
            for index in range(3)
        ]
        for index, content in enumerate(contents):
            Content.objects.filter(pk=content.pk).update(
                created_at=base_time + timedelta(minutes=index)
            )

        response = self.client.get(reverse("analysis_history"), {"page_size": 2})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual(
            [item["file_name"] for item in payload],
            ["history-2.png", "history-1.png"],
        )


class PublicRecentActivityViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="recent-user",
            nickname="recentuser",
            display_name="Recent User",
            email="recent@example.com",
            password="password1234",
        )

    def test_public_recent_activity_returns_frontend_preview_key(self):
        Content.objects.create(
            owner=self.user,
            content_type="image",
            status="allow",
            decision="allow",
            original_file="",
            original_filename="recent.png",
            mime_type="image/png",
            file_size=123,
            reason="등록 승인",
            blockchain={"network_name": "Sepolia"},
        )

        response = self.client.get(reverse("public_recent_activity"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertIn("preview_url", payload[0])
        self.assertNotIn("previewUrl", payload[0])
