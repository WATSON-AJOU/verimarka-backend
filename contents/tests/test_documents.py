from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from analysis.models import AIJob
from analysis.tasks import run_register_analysis_job
from contents.api.services import ContentRegistrationService
from contents.models import Content
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
        self.assertEqual(
            updated.document_metadata["document_type"], "labor_contract_std_v1"
        )

    def test_apply_document_register_result_keeps_verified_decision(self):
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
                "decision": "verified",
                "reason": "document watermarked and OCR summary extracted",
                "document_type": "labor_contract_std_v1",
                "assets": {},
                "watermark": {"applied": True},
                "ocr_summary": {},
                "pending_actions": [],
                "warnings": [],
            },
        )

        self.assertEqual(updated.status, "verified")
        self.assertEqual(updated.decision, "verified")
        self.assertEqual(updated.watermark["document_decision"], "verified")

    def test_apply_document_register_result_keeps_failed_decision(self):
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

        self.assertEqual(updated.status, "failed")
        self.assertEqual(updated.decision, "failed")
        self.assertEqual(updated.watermark["document_decision"], "failed")

    @patch("analysis.tasks.ContentRegistrationService.register_document")
    def test_document_register_failed_decision_marks_ai_job_failure(
        self, mocked_register_document
    ):
        content = Content.objects.create(
            owner=self.user,
            content_type="document",
            status="pending",
            original_file="",
            original_filename="contract.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=1024,
        )
        job = AIJob.objects.create(
            owner=self.user,
            content=content,
            job_type="register",
            request_payload={
                "content_type": "document",
                "source_input": {"s3_key": "document/register_request/contract.docx"},
            },
        )
        content.status = "failed"
        content.decision = "failed"
        content.reason = "libreoffice is required for DOC/DOCX document rendering"
        mocked_register_document.return_value = content

        run_register_analysis_job.apply(args=[str(job.public_id)])

        job.refresh_from_db()
        self.assertEqual(job.status, "failure")
        self.assertEqual(job.error_code, "DOCUMENT_REGISTER_FAILED")


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

    @patch(
        "contents.verification_service.ContentDocumentAIService.run_verify_workflow_v1"
    )
    @patch(
        "contents.verification_service.S3StorageService.is_enabled", return_value=False
    )
    def test_verify_document_returns_manual_review_payload(
        self, _mocked_storage, mocked_verify
    ):
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

    @patch(
        "contents.verification_service.ContentDocumentAIService.run_verify_workflow_v1"
    )
    @patch(
        "contents.verification_service.S3StorageService.is_enabled", return_value=False
    )
    def test_verify_document_accepts_numeric_best_page(
        self, _mocked_storage, mocked_verify
    ):
        mocked_verify.return_value = {
            "success": True,
            "decision": "review",
            "reason": "document watermark not detected",
            "document_type": "labor_contract_std_v1",
            "assets": {"original_s3_key": "document/verify_request/test.pdf"},
            "watermark": {
                "detected": False,
                "payload_id": None,
                "confidence": 0.42,
                "best_page": 2,
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
        self.assertEqual(payload["detect"]["confidence"], 0.42)
        self.assertEqual(payload["detect"]["best_page"], 2)
