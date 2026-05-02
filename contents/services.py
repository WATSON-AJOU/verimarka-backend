import logging
import tempfile
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from analysis.contracts import GuardRequestV1
from analysis.services import AnalysisGuardService

from .document_service import ContentDocumentAIService
from .input_safety import normalize_uploaded_filename, sanitize_uploaded_filename
from .input_safety import resolve_content_type_from_mime
from .models import Content
from .storage import S3StorageService

logger = logging.getLogger(__name__)


class ContentRegistrationService:
    @classmethod
    def write_temp_file_with_hash(cls, upload) -> tuple[Path, str]:
        safe_name = sanitize_uploaded_filename(
            getattr(upload, "name", ""),
            mime_type=getattr(upload, "content_type", "") or None,
        )
        suffix = Path(safe_name).suffix or ".bin"
        digest = sha256()
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        with temp_file as file_handle:
            for chunk in upload.chunks():
                file_handle.write(chunk)
                digest.update(chunk)
        return Path(temp_file.name), digest.hexdigest()

    @classmethod
    def register_image(cls, *, user, upload) -> Content:
        temp_path, source_sha256 = cls.write_temp_file_with_hash(upload)
        content = cls.create_pending_content(user=user, upload=upload, source_sha256=source_sha256)

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
    def register_document(cls, *, content: Content, user, source_input: dict[str, str]) -> Content:
        request_dict = {
            "job_id": str(content.public_id),
            "input": {
                "s3_key": source_input.get("s3_key"),
                "filename": content.original_filename,
                "mime_type": content.mime_type,
            },
            "meta": {
                "user_id": str(user.id),
                "content_id": str(content.public_id),
            },
            "document_type": getattr(settings, "DOC_DEFAULT_TYPE", "labor_contract_std_v1"),
        }
        result = ContentDocumentAIService.run_register_workflow_v1(request_dict)
        return cls.apply_document_register_result(content=content, result=result)

    @classmethod
    def create_pending_content(cls, *, user, upload, source_sha256: str = "") -> Content:
        mime_type = getattr(upload, "content_type", "") or "application/octet-stream"
        content_type = resolve_content_type_from_mime(mime_type)
        display_filename = normalize_uploaded_filename(
            getattr(upload, "name", ""),
            mime_type=mime_type or None,
        )
        content = Content.objects.create(
            owner=user,
            content_type=content_type,
            status="pending",
            original_file="",
            original_filename=display_filename,
            source_sha256=source_sha256,
            mime_type=mime_type,
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
    def create_blocked_duplicate_content(
        cls,
        *,
        user,
        upload,
        source_sha256: str,
        existing_content: Content,
        temp_path: Path | None = None,
    ) -> Content:
        content = cls.create_pending_content(user=user, upload=upload, source_sha256=source_sha256)
        if temp_path is not None:
            try:
                cls._build_source_input(content, temp_path=temp_path)
            except Exception:
                logger.exception(
                    "contents.register.duplicate_blocked.source_input_failed content_id=%s owner_id=%s",
                    content.public_id,
                    content.owner_id,
                )
        content.status = "block"
        content.decision = "block"
        content.reason = (
            f"동일한 원본 파일이 이미 처리되었습니다. "
            f"(기존 콘텐츠 ID: {existing_content.public_id})"
        )
        content.next_action = "none"
        content.top_cosine = 1.0
        content.top_phash_dist = 0
        content.top_match = {
            "public_id": str(existing_content.public_id),
            "db_file": existing_content.original_filename,
            "file_name": existing_content.original_filename,
            "preview_url": cls._resolve_content_image_url(existing_content),
            "owner_name": cls._resolve_owner_name(existing_content),
            "registered_at": timezone.localtime(existing_content.created_at).strftime("%Y.%m.%d %H:%M"),
            "summary": "동일 원본 이미지가 기존 등록 기록과 일치합니다.",
        }
        content.candidates = [content.top_match]
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
                "analyzed_at",
                "updated_at",
            ]
        )
        logger.info(
            "contents.register.duplicate_blocked content_id=%s existing_content_id=%s owner_id=%s source_sha256=%s",
            content.public_id,
            existing_content.public_id,
            content.owner_id,
            source_sha256,
        )
        return content

    @classmethod
    def apply_document_register_result(cls, *, content: Content, result: dict) -> Content:
        watermark = result.get("watermark") or {}
        assets = result.get("assets") or {}
        ocr_summary = result.get("ocr_summary") or {}
        raw_decision = result.get("decision") or "failed"

        if raw_decision == "verified":
            content.status = "allow"
            content.decision = "allow"
            content.reason = result.get("reason") or "문서 등록 처리가 완료되었습니다."
            content.next_action = "none"
        elif raw_decision == "review":
            content.status = "review"
            content.decision = "review"
            content.reason = result.get("reason") or "문서 확인이 필요합니다."
            content.next_action = "start_vote"
        else:
            content.status = "block"
            content.decision = "block"
            content.reason = result.get("reason") or "문서 등록 처리에 실패했습니다."
            content.next_action = "none"

        content.original_storage_key = assets.get("original_s3_key") or content.original_storage_key
        content.watermark = {
            "requested": True,
            "applied": bool(watermark.get("applied")),
            "payload_id": watermark.get("payload_id"),
            "output_key": watermark.get("output_key") or assets.get("watermarked_s3_key"),
            "output_path": watermark.get("output_path"),
            "page_results": watermark.get("page_results") or [],
            "document_decision": raw_decision,
            "pending_actions": result.get("pending_actions") or [],
        }
        content.document_metadata = {
            "document_type": result.get("document_type") or getattr(settings, "DOC_DEFAULT_TYPE", "labor_contract_std_v1"),
            "ocr_summary": ocr_summary,
            "ocr_raw_s3_key": assets.get("ocr_raw_s3_key"),
            "watermarked_s3_key": assets.get("watermarked_s3_key"),
            "warnings": result.get("warnings") or [],
        }
        content.analyzed_at = timezone.now()
        content.save(
            update_fields=[
                "status",
                "decision",
                "reason",
                "next_action",
                "original_storage_key",
                "watermark",
                "document_metadata",
                "analyzed_at",
                "updated_at",
            ]
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
        temp_path, _ = cls.write_temp_file_with_hash(upload)
        return temp_path

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
            stage=(
                settings.S3_PREFIX_DOC_REGISTER_REQUEST
                if content.content_type == "document"
                else settings.CONTENT_ORIGINAL_PREFIX
            ),
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
