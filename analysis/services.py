import importlib
import logging
import sys
from pathlib import Path

from django.conf import settings
from pydantic import ValidationError

from .contracts import (
    GuardErrorResponseV1,
    GuardRequestV1,
    GuardResponseV1,
)

logger = logging.getLogger(__name__)


class AIIntegrationError(Exception):
    def __init__(
        self,
        error_code: str,
        error_message: str,
        retryable: bool,
        status_code: int,
        job_id: str | None = None,
    ):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.retryable = retryable
        self.status_code = status_code
        self.job_id = job_id

    def to_response(self) -> GuardErrorResponseV1:
        return GuardErrorResponseV1(
            job_id=self.job_id,
            error_code=self.error_code,
            error_message=self.error_message,
            retryable=self.retryable,
        )


class AnalysisGuardService:
    _guard_callable = None

    @classmethod
    def run_guard_v1(cls, request_dict: dict) -> GuardResponseV1:
        try:
            request = GuardRequestV1.model_validate(request_dict)
        except ValidationError as exc:
            logger.exception(
                "analysis.guard.invalid_request job_id=%s payload=%s",
                request_dict.get("job_id"),
                request_dict,
            )
            raise AIIntegrationError(
                error_code="INVALID_INPUT",
                error_message=exc.errors()[0]["msg"],
                retryable=False,
                status_code=400,
                job_id=request_dict.get("job_id"),
            ) from exc

        guard_callable = cls._get_guard_callable()
        logger.info(
            "analysis.guard.invoke job_id=%s mode=%s content_type=%s input=%s",
            request.job_id,
            request.mode,
            request.content_type,
            request.input[0].model_dump(exclude_none=True) if request.input else None,
        )

        try:
            response = guard_callable(request.model_dump(exclude_none=True))
        except ValueError as exc:
            logger.exception("analysis.guard.value_error job_id=%s", request.job_id)
            raise AIIntegrationError(
                error_code="INVALID_INPUT",
                error_message=str(exc),
                retryable=False,
                status_code=400,
                job_id=request.job_id,
            ) from exc
        except RuntimeError as exc:
            logger.exception("analysis.guard.runtime_error job_id=%s", request.job_id)
            raise AIIntegrationError(
                error_code="AI_INTERNAL_ERROR",
                error_message=str(exc) or "AI guard execution failed",
                retryable=True,
                status_code=500,
                job_id=request.job_id,
            ) from exc
        except Exception as exc:
            logger.exception("analysis.guard.unexpected_error job_id=%s", request.job_id)
            raise AIIntegrationError(
                error_code="AI_INTERNAL_ERROR",
                error_message=str(exc) or "AI guard execution failed",
                retryable=True,
                status_code=500,
                job_id=request.job_id,
            ) from exc

        try:
            payload = response.model_dump() if hasattr(response, "model_dump") else response
            logger.info(
                "analysis.guard.completed job_id=%s payload=%s",
                request.job_id,
                payload,
            )
            return GuardResponseV1.model_validate(payload)
        except ValidationError as exc:
            logger.exception("analysis.guard.invalid_response job_id=%s payload=%s", request.job_id, payload)
            raise AIIntegrationError(
                error_code="AI_RESPONSE_INVALID",
                error_message=exc.errors()[0]["msg"],
                retryable=False,
                status_code=500,
                job_id=request.job_id,
            ) from exc

    @classmethod
    def _get_guard_callable(cls):
        if cls._guard_callable is not None:
            return cls._guard_callable

        cls._ensure_aimodel_path()

        try:
            module = importlib.import_module("app.guard_service")
            cls._guard_callable = module.run_guard_v1
            return cls._guard_callable
        except ModuleNotFoundError as exc:
            raise AIIntegrationError(
                error_code="AI_DEPENDENCY_MISSING",
                error_message=str(exc),
                retryable=False,
                status_code=500,
            ) from exc

    @classmethod
    def _ensure_aimodel_path(cls):
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
