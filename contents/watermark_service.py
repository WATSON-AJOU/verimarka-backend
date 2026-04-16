import shutil
from pathlib import Path

from django.conf import settings
from django.db import transaction

from analysis.services import AIIntegrationError
from analysis.watermark_services import WatermarkAIService
from contents.blockchain_service import ContentBlockchainService
from .models import Content
from .storage import S3StorageService


class ContentWatermarkService:
    @classmethod
    def apply_watermark(cls, *, content: Content) -> Content:
        with transaction.atomic():
            locked_content = Content.objects.select_for_update().get(pk=content.pk)

            if locked_content.decision != "allow":
                raise AIIntegrationError(
                    error_code="INVALID_STATE",
                    error_message="ALLOW 판정 콘텐츠만 워터마크를 삽입할 수 있습니다.",
                    retryable=False,
                    status_code=400,
                    job_id=str(locked_content.public_id),
                )

            existing_watermark = locked_content.watermark or {}
            if existing_watermark.get("applied") and (
                existing_watermark.get("output_key")
                or existing_watermark.get("output_url")
            ):
                return locked_content

            if existing_watermark.get("processing"):
                raise AIIntegrationError(
                    error_code="WATERMARK_ALREADY_RUNNING",
                    error_message="이미 워터마크 작업이 진행 중입니다.",
                    retryable=True,
                    status_code=409,
                    job_id=str(locked_content.public_id),
                )

            locked_content.watermark = {
                **existing_watermark,
                "requested": True,
                "applied": False,
                "processing": True,
            }
            locked_content.save(update_fields=["watermark", "updated_at"])
            content = locked_content

        existing_watermark = content.watermark or {}
        source_input = cls._build_source_input(content)

        try:
            response = WatermarkAIService.embed(
                {
                    "job_id": str(content.public_id),
                    "input": {
                        **source_input,
                        "filename": content.original_filename,
                        "mime_type": content.mime_type,
                    },
                    "meta": {
                        "user_id": str(content.owner_id),
                        "content_id": str(content.public_id),
                    },
                    "options": {
                        "model": existing_watermark.get("model") or "wam",
                        "nbits": existing_watermark.get("nbits") or 32,
                        "scaling_w": existing_watermark.get("scaling_w") or 2.0,
                        "proportion_masked": existing_watermark.get("proportion_masked") or 0.65,
                    },
                }
            )

            if not response.get("success") or not response.get("result", {}).get("applied"):
                raise AIIntegrationError(
                    error_code="WAM_INFER_FAIL",
                    error_message=response.get("reason") or "워터마크 삽입에 실패했습니다.",
                    retryable=True,
                    status_code=500,
                    job_id=str(content.public_id),
                )

            result = response["result"]
            output_key = result.get("output_key")
            output_url = result.get("output_url")
            output_path = result.get("output_path")

            if not output_key and output_path and S3StorageService.is_enabled():
                output_key = S3StorageService.build_content_key(
                    owner_id=content.owner_id,
                    content_public_id=str(content.public_id),
                    filename=content.original_filename,
                    stage=settings.CONTENT_RESULT_PREFIX,
                )
                S3StorageService.upload_file(
                    local_path=output_path,
                    key=output_key,
                    content_type=content.mime_type,
                )

            if output_key and S3StorageService.is_enabled():
                output_url = S3StorageService.generate_presigned_get_url(key=output_key)
            elif output_path:
                output_url = cls._store_local_result(content, output_path)

            content.watermark = {
                **existing_watermark,
                "requested": True,
                "applied": True,
                "processing": False,
                "output_key": output_key,
                "output_url": output_url,
                "output_path": output_path,
                "payload_id": result.get("payload_id"),
                "model": result.get("model") or existing_watermark.get("model") or "wam",
                "model_version": result.get("model_version"),
                "details": result.get("details") or {},
                "last_error": "",
            }
            content.save(update_fields=["watermark", "updated_at"])
            ContentBlockchainService._ensure_vector_upserted(content=content)
            return content
        except AIIntegrationError as exc:
            latest_watermark = content.watermark or {}
            content.watermark = {
                **latest_watermark,
                "requested": True,
                "applied": False,
                "processing": False,
                "last_error": exc.error_message,
            }
            content.save(update_fields=["watermark", "updated_at"])
            raise

    @classmethod
    def _build_source_input(cls, content: Content) -> dict[str, str]:
        if not S3StorageService.is_enabled():
            return {"local_path": str(Path(content.original_file.path).resolve())}

        key = content.original_storage_key
        if not key:
            key = S3StorageService.build_content_key(
                owner_id=content.owner_id,
                content_public_id=str(content.public_id),
                filename=content.original_filename,
                stage=settings.CONTENT_ORIGINAL_PREFIX,
            )
            S3StorageService.upload_file(
                local_path=content.original_file.path,
                key=key,
                content_type=content.mime_type,
            )
            content.original_storage_key = key
            content.save(update_fields=["original_storage_key", "updated_at"])

        return {
            "url": S3StorageService.generate_presigned_get_url(key=key),
            "s3_key": key,
            "s3_uri": S3StorageService.build_s3_uri(key=key),
        }

    @classmethod
    def _store_local_result(cls, content: Content, output_path: str) -> str:
        destination_dir = (
            Path(settings.MEDIA_ROOT)
            / "contents"
            / str(content.owner_id)
            / str(content.public_id)
            / "watermark"
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / Path(content.original_filename).name
        shutil.copyfile(output_path, destination_path)
        return f"{settings.MEDIA_URL.rstrip('/')}/contents/{content.owner_id}/{content.public_id}/watermark/{destination_path.name}"
