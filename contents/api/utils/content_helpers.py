from datetime import datetime, timedelta
from pathlib import Path

from django.utils import timezone

from contents.models import Content
from contents.preview_service import resolve_content_document_preview_url
from contents.storage import S3StorageService

REVIEW_VOTE_DURATION = timedelta(hours=72)


def build_watermarked_download_name(
    filename: str, *, content_type: str = "image"
) -> str:
    trimmed = (filename or "").strip()
    if not trimmed:
        return "watermarked_VM.pdf" if content_type == "document" else "watermarked_VM"

    dot_index = trimmed.rfind(".")
    if dot_index <= 0 or dot_index == len(trimmed) - 1:
        suffix = ".pdf" if content_type == "document" else ""
        return f"{trimmed}_VM{suffix}"

    extension = ".pdf" if content_type == "document" else trimmed[dot_index:]
    return f"{trimmed[:dot_index]}_VM{extension}"


def build_content_preview_url(request, content: Content) -> str | None:
    if content.content_type == "document":
        preview_url = resolve_content_document_preview_url(content, request=request)
        if preview_url:
            return preview_url

    watermark = content.watermark or {}
    output_key = watermark.get("output_key")
    if output_key and S3StorageService.is_enabled():
        return S3StorageService.generate_presigned_get_url(key=output_key)

    if content.original_storage_key and S3StorageService.is_enabled():
        return S3StorageService.generate_presigned_get_url(
            key=content.original_storage_key
        )

    if not content.original_file:
        return None

    try:
        if not Path(content.original_file.path).exists():
            return None
    except (NotImplementedError, ValueError, OSError):
        return None

    url = content.original_file.url
    return request.build_absolute_uri(url) if request else url


def _parse_vote_datetime(raw):
    if not raw:
        return None
    if isinstance(raw, datetime):
        parsed = raw
    else:
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def get_review_vote_end_time(content: Content):
    vote = (content.blockchain or {}).get("vote") or {}
    end_time = _parse_vote_datetime(vote.get("end_time"))
    if end_time is not None:
        return end_time

    started_at = _parse_vote_datetime(vote.get("started_at"))
    if started_at is not None:
        return started_at + REVIEW_VOTE_DURATION

    minted_at = _parse_vote_datetime((content.blockchain or {}).get("minted_at"))
    if minted_at is not None:
        return minted_at + REVIEW_VOTE_DURATION

    if content.created_at:
        return content.created_at + REVIEW_VOTE_DURATION

    return None


def format_review_vote_summary(content: Content) -> str:
    end_time = get_review_vote_end_time(content)
    if end_time is None:
        return "투표 진행 중"

    remaining = end_time - timezone.now()
    if remaining.total_seconds() <= 0:
        return "투표 마감 및 확인 대기"

    days_left = max(1, int((remaining.total_seconds() + 86399) // 86400))
    return f"투표 진행 중 · D-{days_left}"


def is_vote_still_open(content: Content) -> bool:
    vote = (content.blockchain or {}).get("vote") or {}
    if vote.get("status") != "Pending":
        return False

    end_time = get_review_vote_end_time(content)
    if end_time is None:
        return True

    return end_time > timezone.now()
