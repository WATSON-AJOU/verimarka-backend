import importlib
import logging
import sys
from pathlib import Path

from django.conf import settings

from analysis.services import AIIntegrationError


logger = logging.getLogger(__name__)


class ContentDocumentAIService:
    _register_callable = None
    _verify_callable = None

    @classmethod
    def run_register_workflow_v1(cls, request_dict: dict) -> dict:
        workflow = cls._get_register_callable()
        return cls._run_workflow(workflow=workflow, request_dict=request_dict, action="register")

    @classmethod
    def run_verify_workflow_v1(cls, request_dict: dict) -> dict:
        workflow = cls._get_verify_callable()
        return cls._run_workflow(workflow=workflow, request_dict=request_dict, action="verify")

    @classmethod
    def _run_workflow(cls, *, workflow, request_dict: dict, action: str) -> dict:
        job_id = request_dict.get("job_id")
        logger.info("contents.document.%s_request job_id=%s payload=%s", action, job_id, request_dict)

        try:
            response = workflow(request_dict)
        except ValueError as exc:
            raise AIIntegrationError(
                error_code="INVALID_INPUT",
                error_message=str(exc),
                retryable=False,
                status_code=400,
                job_id=job_id,
            ) from exc
        except Exception as exc:
            raise AIIntegrationError(
                error_code="AI_INTERNAL_ERROR",
                error_message=str(exc) or "문서 AI 처리에 실패했습니다.",
                retryable=True,
                status_code=500,
                job_id=job_id,
            ) from exc

        payload = response.model_dump() if hasattr(response, "model_dump") else response
        watermark = payload.get("watermark") or {}
        if action == "verify" and watermark and not watermark.get("best_page"):
            best_page = None
            for page_result in watermark.get("page_results") or []:
                if best_page is None or (page_result.get("confidence") or 0.0) > (best_page.get("confidence") or 0.0):
                    best_page = page_result
            if best_page:
                payload["watermark"] = {
                    **watermark,
                    "best_page": best_page,
                    "confidence": best_page.get("confidence"),
                }
        logger.info("contents.document.%s_response job_id=%s payload=%s", action, job_id, payload)
        return payload

    @classmethod
    def _get_register_callable(cls):
        if cls._register_callable is not None:
            return cls._register_callable

        module = cls._import_document_module()
        cls._register_callable = module.run_document_register_workflow_v1
        return cls._register_callable

    @classmethod
    def _get_verify_callable(cls):
        if cls._verify_callable is not None:
            return cls._verify_callable

        module = cls._import_document_module()
        cls._verify_callable = module.run_document_verify_workflow_v1
        return cls._verify_callable

    @classmethod
    def _import_document_module(cls):
        cls._ensure_aimodel_path()
        try:
            return importlib.import_module("app.document.workflow_service")
        except ModuleNotFoundError as exc:
            raise AIIntegrationError(
                error_code="AI_DEPENDENCY_MISSING",
                error_message=str(exc),
                retryable=False,
                status_code=500,
            ) from exc

    @classmethod
    def _ensure_aimodel_path(cls) -> None:
        aimodel_root = Path(
            getattr(
                settings,
                "AI_MODEL_ROOT",
                Path(settings.BASE_DIR).parent / "WATSON_WM" / "img_guard",
            )
        ).resolve()

        if not aimodel_root.exists():
            raise AIIntegrationError(
                error_code="AI_MODULE_NOT_FOUND",
                error_message=f"img_guard module not found: {aimodel_root}",
                retryable=False,
                status_code=500,
            )

        aimodel_root_str = str(aimodel_root)
        if aimodel_root_str not in sys.path:
            sys.path.insert(0, aimodel_root_str)
