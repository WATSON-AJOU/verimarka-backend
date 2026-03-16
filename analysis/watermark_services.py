import importlib
import sys
from pathlib import Path
from typing import Any

from django.conf import settings
from pydantic import BaseModel, Field, ValidationError

from .services import AIIntegrationError


class WatermarkMediaInput(BaseModel):
    url: str | None = None
    s3_uri: str | None = None
    s3_key: str | None = None
    local_path: str | None = None
    filename: str | None = None
    mime_type: str | None = None


class WatermarkEmbedOptions(BaseModel):
    model: str = "wam"
    nbits: int = 32
    scaling_w: float = 2.0
    proportion_masked: float = 0.35
    seed: int | None = None


class WatermarkDetectOptions(BaseModel):
    model: str = "wam"
    threshold: float = 0.5


class WatermarkEmbedRequest(BaseModel):
    job_id: str
    input: WatermarkMediaInput
    meta: dict[str, Any] = Field(default_factory=dict)
    options: WatermarkEmbedOptions = WatermarkEmbedOptions()
    payload_id: str | None = None


class WatermarkDetectRequest(BaseModel):
    job_id: str
    input: WatermarkMediaInput
    options: WatermarkDetectOptions = WatermarkDetectOptions()


class WatermarkAIService:
    _service_factory = None

    @classmethod
    def embed(cls, request_dict: dict) -> dict:
        request = cls._validate_request(WatermarkEmbedRequest, request_dict)
        service = cls._get_service_instance()

        try:
            response = service.embed(request)
            return response.model_dump() if hasattr(response, "model_dump") else response
        except Exception as exc:
            raise AIIntegrationError(
                error_code="AI_INTERNAL_ERROR",
                error_message=str(exc) or "AI watermark embed failed",
                retryable=True,
                status_code=500,
                job_id=request.job_id,
            ) from exc

    @classmethod
    def detect(cls, request_dict: dict) -> dict:
        request = cls._validate_request(WatermarkDetectRequest, request_dict)
        service = cls._get_service_instance()

        try:
            response = service.detect(request)
            return response.model_dump() if hasattr(response, "model_dump") else response
        except Exception as exc:
            raise AIIntegrationError(
                error_code="AI_INTERNAL_ERROR",
                error_message=str(exc) or "AI watermark detect failed",
                retryable=True,
                status_code=500,
                job_id=request.job_id,
            ) from exc

    @classmethod
    def _validate_request(cls, schema: type[BaseModel], request_dict: dict):
        try:
            return schema.model_validate(request_dict)
        except ValidationError as exc:
            raise AIIntegrationError(
                error_code="INVALID_INPUT",
                error_message=exc.errors()[0]["msg"],
                retryable=False,
                status_code=400,
                job_id=request_dict.get("job_id"),
            ) from exc

    @classmethod
    def _get_service_instance(cls):
        service_factory = cls._get_service_factory()
        return service_factory()

    @classmethod
    def _get_service_factory(cls):
        if cls._service_factory is not None:
            return cls._service_factory

        cls._ensure_aimodel_path()

        try:
            module = importlib.import_module("app.watermark.service")
            cls._service_factory = module.WatermarkService.create
            return cls._service_factory
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
