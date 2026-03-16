import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from analysis.contracts import GuardRequestV1
from analysis.services import AnalysisGuardService

from .models import Content
from .storage import S3StorageService

logger = logging.getLogger(__name__)


class ContentRegistrationService:
    @classmethod
    def register_image(cls, *, user, upload) -> Content:
        content = Content.objects.create(
            owner=user,
            content_type="image",
            status="pending",
            original_file=upload,
            original_filename=upload.name,
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

        source_input = cls._build_source_input(content)
        logger.info(
            "contents.register.source_input content_id=%s source_input=%s",
            content.public_id,
            source_input,
        )

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
                "user_id": str(user.id),
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
        content.top_match = response.top_match.model_dump() if response.top_match else {}
        content.candidates = [candidate.model_dump() for candidate in response.candidates]
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
    def _build_source_input(cls, content: Content) -> dict[str, str]:
        if not S3StorageService.is_enabled():
            resolved_path = str(Path(content.original_file.path).resolve())
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
            stage=settings.CONTENT_CANDIDATE_PREFIX,
        )
        S3StorageService.upload_file(
            local_path=content.original_file.path,
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
