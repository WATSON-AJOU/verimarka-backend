from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from contents.blockchain_service import ContentBlockchainService
from contents.models import Content
from wallets.models import WalletLink

User = get_user_model()


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
            original_file=SimpleUploadedFile(
                filename, b"fake-image-bytes", content_type="image/png"
            ),
            original_filename=filename,
            mime_type="image/png",
            file_size=16,
            watermark={
                "applied": True,
                "payload_id": 4242,
                "model": "wam",
                "model_version": "v2",
            },
        )

    @patch.object(
        ContentBlockchainService,
        "_ensure_vector_upserted",
        side_effect=lambda *, content: content,
    )
    @patch.object(
        ContentBlockchainService,
        "_load_watermarked_bytes",
        return_value=b"watermarked-bytes",
    )
    @patch.object(ContentBlockchainService, "_create_client")
    def test_mint_passes_and_persists_file_name(
        self, mocked_create_client, _mocked_load_bytes, _mocked_upsert
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

        content = self._create_content(
            decision="allow", status="allow", filename="origin-name.png"
        )
        updated = ContentBlockchainService.mint(content=content)

        blockchain.mint_document_with_metadata.assert_called_once()
        self.assertEqual(updated.blockchain["file_name"], "minted-name.png")
        self.assertEqual(updated.blockchain["document"]["file_name"], "minted-name.png")

    @patch.object(
        ContentBlockchainService,
        "_ensure_vector_upserted",
        side_effect=lambda *, content: content,
    )
    @patch.object(ContentBlockchainService, "_create_client")
    def test_mint_repairs_existing_broken_mint_record_without_reminting(
        self, mocked_create_client, _mocked_upsert
    ):
        blockchain = Mock()
        blockchain.chain_id = 137
        blockchain.contract_address = "0xabc"
        blockchain.verify_document.return_value = {
            "exists": True,
            "token_id": 21,
            "owner": "0x0000000000000000000000000000000000000000",
            "status": "Approved",
            "verification_link": "https://example.com/verify/21",
            "author_name": "Chain User",
            "file_name": "broken-name.png",
        }
        blockchain.get_token_id_by_wm_id.return_value = 21
        blockchain.get_document_info.return_value = {
            "status": "Approved",
            "upvotes": 0,
            "downvotes": 0,
            "end_time": 0,
            "file_hash": b"\x13" * 32,
            "timestamp": 1710000000,
            "author_name": "Chain User",
            "file_name": "broken-name.png",
        }
        mocked_create_client.return_value = blockchain

        content = self._create_content(
            decision="allow", status="allow", filename="broken-name.png"
        )
        content.blockchain = {
            "minted": True,
            "mint_kind": "content",
            "tx_hash": "0xexisting",
            "wm_id": 4242,
            "token_id": 0,
            "owner_address": "0x0000000000000000000000000000000000000000",
        }
        content.save(update_fields=["blockchain", "updated_at"])

        updated = ContentBlockchainService.mint(content=content)

        blockchain.mint_document_with_metadata.assert_not_called()
        self.assertEqual(updated.blockchain["token_id"], 21)

    @patch("contents.blockchain_service.urlopen")
    def test_load_watermarked_bytes_supports_absolute_output_url(self, mocked_urlopen):
        mocked_response = Mock()
        mocked_response.read.return_value = b"remote-watermarked-bytes"
        mocked_urlopen.return_value.__enter__.return_value = mocked_response

        content = self._create_content(
            decision="allow", status="allow", filename="origin-name.png"
        )
        content.watermark = {
            "applied": True,
            "payload_id": 4242,
            "output_url": "https://example.com/watermarked.png",
        }

        result = ContentBlockchainService._load_watermarked_bytes(content)

        self.assertEqual(result, b"remote-watermarked-bytes")
        mocked_urlopen.assert_called_once_with(
            "https://example.com/watermarked.png", timeout=10
        )

    def test_classify_blockchain_timeout_hides_raw_rpc_message(self):
        error_code, error_message, retryable, status_code = (
            ContentBlockchainService._classify_blockchain_error(
                TimeoutError("HTTPConnectionPool read timed out after 30 seconds"),
                fallback_code="BLOCKCHAIN_MINT_FAIL",
                fallback_message="NFT 토큰 발행에 실패했습니다.",
                fallback_status_code=500,
            )
        )

        self.assertEqual(error_code, "BLOCKCHAIN_RPC_TIMEOUT")
        self.assertEqual(
            error_message,
            "블록체인 네트워크 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.",
        )
        self.assertTrue(retryable)
        self.assertEqual(status_code, 503)

    def test_classify_blockchain_vote_revert_to_user_message(self):
        error_code, error_message, retryable, status_code = (
            ContentBlockchainService._classify_blockchain_error(
                RuntimeError("execution reverted: Already voted"),
                fallback_code="BLOCKCHAIN_VOTE_CAST_FAIL",
                fallback_message="서명 기반 투표 처리에 실패했습니다.",
                fallback_status_code=400,
            )
        )

        self.assertEqual(error_code, "BLOCKCHAIN_VOTE_ALREADY_CAST")
        self.assertEqual(error_message, "이미 이 투표에 참여했습니다.")
        self.assertFalse(retryable)
        self.assertEqual(status_code, 409)

    @patch.object(ContentBlockchainService, "_create_client")
    def test_sync_review_vote_finalizes_pending_vote_after_72_hours_without_end_time(
        self, mocked_create_client
    ):
        blockchain = Mock()
        blockchain.chain_id = 11155111
        blockchain.contract_address = "0xabc"
        old_timestamp = int((timezone.now() - timedelta(days=4)).timestamp())
        blockchain.verify_document.side_effect = [
            {
                "exists": True,
                "token_id": 77,
                "owner": "0x1234567890123456789012345678901234567890",
                "status": "Pending",
                "verification_link": "https://example.com/verify/77",
                "author_name": "Chain User",
                "file_name": "review-name.png",
            },
            {
                "exists": True,
                "token_id": 77,
                "owner": "0x1234567890123456789012345678901234567890",
                "status": "Approved",
                "verification_link": "https://example.com/verify/77",
                "author_name": "Chain User",
                "file_name": "review-name.png",
            },
        ]
        blockchain.get_document_info.side_effect = [
            {
                "status": "Pending",
                "upvotes": 2,
                "downvotes": 0,
                "end_time": 0,
                "timestamp": old_timestamp,
                "author_name": "Chain User",
                "file_name": "review-name.png",
            },
            {
                "status": "Approved",
                "upvotes": 2,
                "downvotes": 0,
                "end_time": 0,
                "timestamp": old_timestamp,
                "author_name": "Chain User",
                "file_name": "review-name.png",
            },
        ]
        mocked_create_client.return_value = blockchain

        content = self._create_content(
            decision="review", status="review", filename="review-name.png"
        )
        content.blockchain = {
            "minted": True,
            "mint_kind": "review_vote",
            "wm_id": 4242,
            "token_id": 77,
            "recipient_address": "0x1234567890123456789012345678901234567890",
            "vote": {"status": "Pending", "vote_id": "VOTE-77"},
        }
        content.save(update_fields=["blockchain", "updated_at"])

        updated = ContentBlockchainService.sync_review_vote(content=content)

        blockchain.finalize_status.assert_called_once_with(77)
        self.assertEqual(updated.blockchain["vote"]["status"], "Approved")
        self.assertIsNotNone(updated.blockchain["vote"]["end_time"])
        self.assertEqual(updated.decision, "allow")
