from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analysis.contracts import (
    GuardCandidateV1,
    GuardResponseV1,
    GuardScoresV1,
    GuardTimingV1,
    GuardWatermarkResultV1,
)
from analysis.models import AIJob
from analysis.services import AIIntegrationError
from logs.models import VerificationHistoryLog
from wallets.models import WalletLink
from .blockchain_service import ContentBlockchainService
from .models import Content
from .verification_service import ContentVerificationService
from .watermark_service import ContentWatermarkService


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
        self.assertEqual(content.original_filename, "evil file!!.png")

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


class ContentVerifyFilenameTests(TestCase):
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
    def test_verify_result_preserves_display_filename(
        self,
        mocked_detect,
        mocked_guard,
        _mocked_storage,
    ):
        mocked_detect.return_value = {
            "success": True,
            "result": {
                "detected": False,
                "payload_id": None,
                "confidence": 0.0,
                "bit_accuracy": 0.0,
            },
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

        upload = SimpleUploadedFile(
            "../../verify file!!.png",
            b"\x89PNG\r\n\x1a\nverifycontent",
            content_type="image/png",
        )
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


class ContentBlockchainFilenameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="chainuser",
            nickname="chainuser",
            display_name="Chain User",
            email="chainuser@example.com",
            password="password1234",
            phone="01055556666",
            phone_verified=True,
        )
        WalletLink.objects.create(
            user=self.user,
            address="0x1234567890123456789012345678901234567890",
            verified_at=timezone.now(),
        )

    def _create_content(self, *, decision: str, status: str, filename: str) -> Content:
        return Content.objects.create(
            owner=self.user,
            content_type="image",
            status=status,
            decision=decision,
            original_file=SimpleUploadedFile(filename, b"fake-image-bytes", content_type="image/png"),
            original_filename=filename,
            mime_type="image/png",
            file_size=16,
            watermark={"applied": True, "payload_id": 4242, "model": "wam", "model_version": "v2"},
        )

    @patch.object(ContentBlockchainService, "_ensure_vector_upserted", side_effect=lambda *, content: content)
    @patch.object(ContentBlockchainService, "_load_watermarked_bytes", return_value=b"watermarked-bytes")
    @patch.object(ContentBlockchainService, "_create_client")
    def test_mint_passes_and_persists_file_name(
        self,
        mocked_create_client,
        _mocked_load_bytes,
        _mocked_upsert,
    ):
        blockchain = Mock()
        blockchain.chain_id = 11155111
        blockchain.contract_address = "0xabc"
        blockchain.compute_file_hash_sha256.return_value = b"\x11" * 32
        blockchain.mint_document_with_metadata.return_value = {
            "tx_hash": "0xtx",
            "block_number": 10,
            "gas_used": 12345,
            "token_uri": "ipfs://token",
        }
        blockchain.verify_document.return_value = {
            "exists": True,
            "token_id": 7,
            "owner": "0x1234567890123456789012345678901234567890",
            "status": "Approved",
            "verification_link": "https://example.com/verify/7",
            "author_name": "Chain User",
            "file_name": "minted-name.png",
        }
        blockchain.get_document_info.return_value = {
            "status": "Approved",
            "upvotes": 0,
            "downvotes": 0,
            "end_time": 0,
            "file_hash": b"\x11" * 32,
            "timestamp": 1710000000,
            "author_name": "Chain User",
            "file_name": "minted-name.png",
        }
        mocked_create_client.return_value = blockchain

        content = self._create_content(decision="allow", status="allow", filename="origin-name.png")
        updated = ContentBlockchainService.mint(content=content)

        blockchain.mint_document_with_metadata.assert_called_once_with(
            to="0x1234567890123456789012345678901234567890",
            wm_id=4242,
            file_hash=b"\x11" * 32,
            author_name="Chain User",
            file_name="origin-name.png",
            is_suspicious=False,
        )
        self.assertEqual(updated.blockchain["file_name"], "minted-name.png")
        self.assertEqual(updated.blockchain["document"]["file_name"], "minted-name.png")

    @patch("contents.blockchain_service.urlopen")
    def test_load_watermarked_bytes_supports_absolute_output_url(
        self,
        mocked_urlopen,
    ):
        mocked_response = Mock()
        mocked_response.read.return_value = b"remote-watermarked-bytes"
        mocked_urlopen.return_value.__enter__.return_value = mocked_response

        content = self._create_content(decision="allow", status="allow", filename="origin-name.png")
        content.watermark = {
            "applied": True,
            "payload_id": 4242,
            "output_url": "https://example.com/watermarked.png",
        }

        result = ContentBlockchainService._load_watermarked_bytes(content)

        self.assertEqual(result, b"remote-watermarked-bytes")
        mocked_urlopen.assert_called_once_with("https://example.com/watermarked.png", timeout=10)

    @patch.object(ContentBlockchainService, "_load_original_bytes", return_value=b"original-bytes")
    @patch.object(ContentBlockchainService, "_create_client")
    def test_review_vote_flow_keeps_file_name(
        self,
        mocked_create_client,
        _mocked_load_original_bytes,
    ):
        blockchain = Mock()
        blockchain.chain_id = 11155111
        blockchain.contract_address = "0xabc"
        blockchain.compute_file_hash_sha256.return_value = b"\x22" * 32
        blockchain.is_file_hash_used.return_value = False
        blockchain.mint_document_with_metadata.return_value = {
            "tx_hash": "0xtx2",
            "block_number": 11,
            "gas_used": 22345,
            "token_uri": "ipfs://vote-token",
        }
        blockchain.verify_document.return_value = {
            "exists": True,
            "token_id": 9,
            "owner": "0x1234567890123456789012345678901234567890",
            "status": "Pending",
            "verification_link": "https://example.com/verify/9",
            "author_name": "Chain User",
            "file_name": "vote-name.png",
        }
        blockchain.get_document_info.return_value = {
            "status": "Pending",
            "upvotes": 0,
            "downvotes": 0,
            "end_time": 1710003600,
            "file_hash": b"\x22" * 32,
            "timestamp": 1710000000,
            "author_name": "Chain User",
            "file_name": "vote-name.png",
        }
        mocked_create_client.return_value = blockchain

        content = self._create_content(decision="review", status="review", filename="review-origin.png")
        updated = ContentBlockchainService.start_review_vote(content=content)

        blockchain.mint_document_with_metadata.assert_called_once_with(
            to="0x1234567890123456789012345678901234567890",
            wm_id=4242,
            file_hash=b"\x22" * 32,
            author_name="Chain User",
            file_name="review-origin.png",
            is_suspicious=True,
        )
        self.assertEqual(updated.blockchain["file_name"], "vote-name.png")
        self.assertEqual(updated.blockchain["document"]["file_name"], "vote-name.png")

    @patch.object(ContentBlockchainService, "_load_original_bytes", return_value=b"original-bytes")
    @patch.object(ContentBlockchainService, "_create_client")
    def test_start_review_vote_persists_notify_by_email(
        self,
        mocked_create_client,
        _mocked_load_original_bytes,
    ):
        blockchain = Mock()
        blockchain.chain_id = 11155111
        blockchain.contract_address = "0xabc"
        blockchain.compute_file_hash_sha256.return_value = b"\x23" * 32
        blockchain.is_file_hash_used.return_value = False
        blockchain.mint_document_with_metadata.return_value = {
            "tx_hash": "0xtx3",
            "block_number": 12,
            "gas_used": 32345,
            "token_uri": "ipfs://vote-token-2",
        }
        blockchain.verify_document.return_value = {
            "exists": True,
            "token_id": 10,
            "owner": "0x1234567890123456789012345678901234567890",
            "status": "Pending",
            "verification_link": "https://example.com/verify/10",
            "author_name": "Chain User",
            "file_name": "vote-name-2.png",
        }
        blockchain.get_document_info.return_value = {
            "status": "Pending",
            "upvotes": 0,
            "downvotes": 0,
            "end_time": 1710003600,
            "file_hash": b"\x23" * 32,
            "timestamp": 1710000000,
            "author_name": "Chain User",
            "file_name": "vote-name-2.png",
        }
        mocked_create_client.return_value = blockchain

        content = self._create_content(decision="review", status="review", filename="review-notify.png")
        updated = ContentBlockchainService.start_review_vote(content=content, notify_by_email=True)

        self.assertTrue(updated.blockchain["vote"]["notify_by_email"])
        self.assertFalse(updated.blockchain["vote"]["email_notification_sent"])

    @patch("contents.blockchain_service.send_review_vote_result_email")
    @patch.object(ContentBlockchainService, "_create_client")
    def test_sync_review_vote_sends_result_email_only_once(
        self,
        mocked_create_client,
        mocked_send_email,
    ):
        blockchain = Mock()
        blockchain.chain_id = 11155111
        blockchain.contract_address = "0xabc"
        blockchain.verify_document.return_value = {
            "exists": True,
            "token_id": 11,
            "owner": "0x1234567890123456789012345678901234567890",
            "status": "Approved",
            "verification_link": "https://example.com/verify/11",
            "author_name": "Chain User",
            "file_name": "vote-approved.png",
        }
        blockchain.get_document_info.return_value = {
            "status": "Approved",
            "upvotes": 8,
            "downvotes": 2,
            "end_time": 1710003600,
            "file_hash": b"\x24" * 32,
            "timestamp": 1710000000,
            "author_name": "Chain User",
            "file_name": "vote-approved.png",
        }
        mocked_create_client.return_value = blockchain

        content = self._create_content(decision="review", status="review", filename="vote-approved.png")
        content.watermark = {"applied": False}
        content.blockchain = {
            "minted": True,
            "mint_kind": "review_vote",
            "recipient_address": "0x1234567890123456789012345678901234567890",
            "wm_id": 4242,
            "token_id": 11,
            "author_name": "Chain User",
            "file_name": "vote-approved.png",
            "vote": {
                "status": "Pending",
                "notify_by_email": True,
                "email_notification_sent": False,
            },
        }
        content.save(update_fields=["watermark", "blockchain", "updated_at"])

        updated = ContentBlockchainService.sync_review_vote(content=content)
        updated.refresh_from_db()

        mocked_send_email.assert_called_once()
        self.assertTrue(updated.blockchain["vote"]["email_notification_sent"])
        self.assertEqual(updated.status, "allow")
        self.assertEqual(updated.decision, "allow")

        ContentBlockchainService.sync_review_vote(content=updated)
        mocked_send_email.assert_called_once()


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
    def test_apply_watermark_resets_processing_on_unexpected_error(
        self,
        _mocked_storage,
        _mocked_embed,
        _mocked_upsert,
    ):
        content = self._create_content()

        with self.assertRaises(AIIntegrationError) as exc:
            ContentWatermarkService.apply_watermark(content=content)

        content.refresh_from_db()
        self.assertEqual(exc.exception.error_code, "WATERMARK_PROCESSING_FAIL")
        self.assertFalse(content.watermark.get("processing"))
        self.assertFalse(content.watermark.get("applied"))
        self.assertEqual(content.watermark.get("last_error"), "embed exploded")
