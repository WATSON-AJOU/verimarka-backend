from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from analysis.contracts import GuardRequestV1
from analysis.services import AnalysisGuardService

from .models import Content
from .storage import S3StorageService


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

        source_url = cls._build_source_url(content)

        guard_request = GuardRequestV1(
            job_id=str(content.public_id),
            mode="register",
            content_type="image",
            input=[
                {
                    "url": source_url,
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

        response = AnalysisGuardService.run_guard_v1(guard_request.model_dump())

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

    @staticmethod
    def _build_file_url(path: str) -> str:
        resolved = Path(path).resolve().as_posix()
        return f"file://{quote(resolved)}"

    @classmethod
    def _build_source_url(cls, content: Content) -> str:
        if not S3StorageService.is_enabled():
            return cls._build_file_url(content.original_file.path)

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
        content.original_storage_key = key
        content.save(update_fields=["original_storage_key", "updated_at"])
        return S3StorageService.generate_presigned_get_url(key=key)
