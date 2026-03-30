import logging
import tempfile
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from analysis.contracts import GuardRequestV1
from analysis.services import AnalysisGuardService

from .input_safety import sanitize_uploaded_filename
from .models import Content
from .storage import S3StorageService

logger = logging.getLogger(__name__)


class ContentRegistrationService:
    @classmethod
    def register_image(cls, *, user, upload) -> Content:
        temp_path = cls._write_temp_file(upload)
        content = cls.create_pending_content(user=user, upload=upload)

        try:
            source_input = cls._build_source_input(content, temp_path=temp_path)
            logger.info(
                "contents.register.source_input content_id=%s source_input=%s",
                content.public_id,
                source_input,
            )

            return cls.run_guard_for_content(content=content, user_id=user.id, source_input=source_input)
        finally:
            temp_path.unlink(missing_ok=True)

    @classmethod
    def create_pending_content(cls, *, user, upload) -> Content:
        safe_filename = sanitize_uploaded_filename(
            getattr(upload, "name", ""),
            mime_type=getattr(upload, "content_type", "") or None,
        )
        upload.name = safe_filename
        content = Content.objects.create(
            owner=user,
            content_type="image",
            status="pending",
            original_file="",
            original_filename=safe_filename,
            mime_type=(getattr(upload, "content_type", "") or "application/octet-stream"),
            file_size=upload.size,
        )

        logger.info(
            "contents.register.created content_id=%s owner_id=%s file=%s mime=%s size=%s",
            content.public_id,
            content.owner_id,
            content.original_filename,
            content.mime_type,
            content.file_size,
        )
        return content

    @classmethod
    def run_guard_for_content(cls, *, content: Content, user_id: int, source_input: dict[str, str]) -> Content:
        guard_request = GuardRequestV1(
            job_id=str(content.public_id),
            mode="register",
            content_type="image",
            input=[
                {
                    **source_input,
                    "filename": content.original_filename,
                    "mime_type": content.mime_type,
                }
            ],
            meta={
                "user_id": str(user_id),
                "content_id": str(content.public_id),
            },
            options={},
        )

        logger.info(
            "contents.register.guard_request content_id=%s payload=%s",
            content.public_id,
            guard_request.model_dump(exclude_none=True),
        )

        response = AnalysisGuardService.run_guard_v1(guard_request.model_dump())
        logger.info(
            "contents.register.guard_response content_id=%s decision=%s reason=%s top_cosine=%s top_phash=%s top_match=%s",
            content.public_id,
            response.decision,
            response.reason,
            response.scores.top_cosine,
            response.scores.top_phash_dist,
            response.top_match.model_dump() if response.top_match else None,
        )

        content.status = response.decision
        content.decision = response.decision
        content.reason = response.reason
        content.next_action = response.next_action
        content.top_cosine = response.scores.top_cosine
        content.top_phash_dist = response.scores.top_phash_dist
        content.top_match = cls._enrich_match(response.top_match.model_dump() if response.top_match else {})
        content.candidates = [cls._enrich_match(candidate.model_dump()) for candidate in response.candidates]
        content.watermark = response.watermark.model_dump()
        content.timing_ms = response.timing_ms.model_dump()
        content.analyzed_at = timezone.now()
        content.save(
            update_fields=[
                "status",
                "decision",
                "reason",
                "next_action",
                "top_cosine",
                "top_phash_dist",
                "top_match",
                "candidates",
                "watermark",
                "timing_ms",
                "analyzed_at",
                "updated_at",
            ]
        )
        return content

    @classmethod
    def _write_temp_file(cls, upload) -> Path:
        safe_name = sanitize_uploaded_filename(
            getattr(upload, "name", ""),
            mime_type=getattr(upload, "content_type", "") or None,
        )
        upload.name = safe_name
        suffix = Path(safe_name).suffix or ".bin"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        with temp_file as file_handle:
            for chunk in upload.chunks():
                file_handle.write(chunk)
        return Path(temp_file.name)

    @classmethod
    def _build_source_input(cls, content: Content, *, temp_path: Path) -> dict[str, str]:
        if not S3StorageService.is_enabled():
            resolved_path = str(temp_path.resolve())
            logger.info(
                "contents.register.source_mode content_id=%s mode=local path=%s",
                content.public_id,
                resolved_path,
            )
            return {
                # Same-runtime function call integration can pass an actual local path.
                "url": resolved_path,
            }

        key = S3StorageService.build_content_key(
            owner_id=content.owner_id,
            content_public_id=str(content.public_id),
            filename=content.original_filename,
            stage=settings.CONTENT_ORIGINAL_PREFIX,
        )
        S3StorageService.upload_file(
            local_path=str(temp_path),
            key=key,
            content_type=content.mime_type,
        )
        logger.info(
            "contents.register.source_mode content_id=%s mode=s3 key=%s bucket=%s",
            content.public_id,
            key,
            settings.AWS_STORAGE_BUCKET_NAME,
        )
        content.original_storage_key = key
        content.save(update_fields=["original_storage_key", "updated_at"])
        return {
            "url": S3StorageService.generate_presigned_get_url(key=key),
            "s3_key": key,
            "s3_uri": S3StorageService.build_s3_uri(key=key),
        }

    @classmethod
    def _enrich_match(cls, match: dict) -> dict:
        if not match:
            return {}

        db_key = match.get("db_key")
        if not db_key:
            return match

        candidate = cls._find_content_by_db_key(db_key)
        if not candidate:
            return match

        return {
            **match,
            "preview_url": cls._resolve_content_image_url(candidate),
            "public_id": str(candidate.public_id),
            "owner_name": cls._resolve_owner_name(candidate),
            "registered_at": timezone.localtime(candidate.created_at).strftime("%Y.%m.%d %H:%M"),
        }

    @classmethod
    def _find_content_by_db_key(cls, db_key: str) -> Content | None:
        return (
            Content.objects.filter(decision="allow")
            .filter(Q(original_storage_key=db_key) | Q(watermark__output_key=db_key))
            .select_related("owner")
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def _resolve_content_image_url(cls, content: Content | None) -> str | None:
        if not content:
            return None

        watermark = content.watermark or {}
        output_key = watermark.get("output_key")
        output_url = watermark.get("output_url")

        if output_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=output_key)

        if output_url:
            if output_url.startswith(("http://", "https://")):
                return output_url
            base_url = getattr(settings, "VERIMARKA_PUBLIC_BASE_URL", "https://verimarka.com").rstrip("/")
            return f"{base_url}{output_url}"

        if content.original_storage_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=content.original_storage_key)

        if content.original_file:
            return content.original_file.url

        return None

    @classmethod
    def _resolve_owner_name(cls, content: Content | None) -> str | None:
        if not content:
            return None

        owner = getattr(content, "owner", None)
        if not owner:
            return None

        return owner.display_name or owner.nickname or owner.username or owner.email
