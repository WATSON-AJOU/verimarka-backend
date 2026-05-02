from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from contents.models import Content
from contents.services import ContentRegistrationService
from contents.verification_service import ContentVerificationService


User = get_user_model()


class ContentDocumentRegistrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="doccreator",
            nickname="doccreator",
            display_name="Doc Creator",
            email="doccreator@example.com",
            password="password1234",
            phone="01099990000",
            phone_verified=True,
        )

    def test_apply_document_register_result_persists_document_metadata(self):
        content = Content.objects.create(
            owner=self.user,
            content_type="document",
            status="pending",
            original_file="",
            original_filename="contract.pdf",
            mime_type="application/pdf",
            file_size=1024,
        )

        updated = ContentRegistrationService.apply_document_register_result(
            content=content,
            result={
                "success": True,
                "decision": "review",
                "reason": "document watermarked; OCR summary unavailable or skipped",
                "document_type": "labor_contract_std_v1",
                "assets": {
                    "original_s3_key": "document/register_request/contract.pdf",
                    "watermarked_s3_key": "document/watermarked/contract_watermarked.pdf",
                    "ocr_raw_s3_key": "document/ocr_raw/contract.json",
                },
                "watermark": {
                    "applied": True,
                    "payload_id": "4242",
                    "output_key": "document/watermarked/contract_watermarked.pdf",
                    "output_path": "/tmp/contract_watermarked.pdf",
                    "page_results": [{"page": 1, "applied": True}],
                },
                "ocr_summary": {
                    "representative_name": {"value": "대표자"},
                    "worker_name": {"value": "근로자"},
                    "written_date": {"value": "2026-05-02"},
                },
                "pending_actions": ["mint_token_with_existing_image_fields"],
                "warnings": [],
            },
        )

        self.assertEqual(updated.status, "review")
        self.assertEqual(updated.decision, "review")
        self.assertEqual(updated.watermark["document_decision"], "review")
        self.assertEqual(updated.document_metadata["document_type"], "labor_contract_std_v1")

    def test_apply_document_register_result_maps_failed_to_block(self):
        content = Content.objects.create(
            owner=self.user,
            content_type="document",
            status="pending",
            original_file="",
            original_filename="contract.pdf",
            mime_type="application/pdf",
            file_size=1024,
        )

        updated = ContentRegistrationService.apply_document_register_result(
            content=content,
            result={
                "success": False,
                "decision": "failed",
                "reason": "render failed",
                "document_type": "labor_contract_std_v1",
                "assets": {},
                "watermark": {},
                "ocr_summary": None,
                "pending_actions": [],
                "warnings": [],
            },
        )

        self.assertEqual(updated.status, "block")
        self.assertEqual(updated.decision, "block")


class ContentDocumentVerifyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="docverifier",
            nickname="docverifier",
            display_name="Doc Verifier",
            email="docverifier@example.com",
            password="password1234",
            phone="01088880000",
            phone_verified=True,
        )

    @patch("contents.verification_service.ContentDocumentAIService.run_verify_workflow_v1")
    @patch("contents.verification_service.S3StorageService.is_enabled", return_value=False)
    def test_verify_document_returns_manual_review_payload(self, _mocked_storage, mocked_verify):
        mocked_verify.return_value = {
            "success": True,
            "decision": "review",
            "reason": "document watermark not detected; manual or token check required",
            "document_type": "labor_contract_std_v1",
            "assets": {"original_s3_key": "document/verify_request/test.pdf"},
            "watermark": {
                "detected": False,
                "payload_id": None,
                "best_page": {"page": 2, "confidence": 0.42},
                "page_results": [],
            },
            "ocr_summary": None,
            "pending_actions": ["manual_review"],
        }

        payload = ContentVerificationService.verify_from_source_input(
            user=self.user,
            upload_name="contract.pdf",
            upload_size=1024,
            upload_content_type="application/pdf",
            content_type="document",
            source_input={"s3_key": "document/verify_request/test.pdf"},
        )

        self.assertEqual(payload["outcome"], "candidate")
        self.assertEqual(payload["detect"]["status_label"], "확인 필요")
        self.assertEqual(payload["detect"]["best_page"], 2)
