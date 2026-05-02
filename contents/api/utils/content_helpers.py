from datetime import datetime
from pathlib import Path

from django.utils import timezone

from contents.models import Content
from contents.storage import S3StorageService


def build_watermarked_download_name(filename: str, *, content_type: str = "image") -> str:
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
    watermark = content.watermark or {}
    output_key = watermark.get("output_key")
    if output_key and S3StorageService.is_enabled():
        return S3StorageService.generate_presigned_get_url(key=output_key)

    if content.original_storage_key and S3StorageService.is_enabled():
        return S3StorageService.generate_presigned_get_url(key=content.original_storage_key)

    if not content.original_file:
        return None

    try:
        if not Path(content.original_file.path).exists():
            return None
    except (NotImplementedError, ValueError, OSError):
        return None

    url = content.original_file.url
    return request.build_absolute_uri(url) if request else url


def format_review_vote_summary(content: Content) -> str:
    vote = (content.blockchain or {}).get("vote") or {}
    end_time_raw = vote.get("end_time")
    if not end_time_raw:
        return "투표 진행 중"

    try:
        end_time = datetime.fromisoformat(str(end_time_raw))
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time, timezone.get_current_timezone())
    except ValueError:
        return "투표 진행 중"

    remaining = end_time - timezone.now()
    if remaining.total_seconds() <= 0:
        return "투표 마감 대기"

    days_left = max(1, int((remaining.total_seconds() + 86399) // 86400))
    return f"투표 진행 중 · D-{days_left}"


def is_vote_still_open(content: Content) -> bool:
    vote = (content.blockchain or {}).get("vote") or {}
    if vote.get("status") != "Pending":
        return False

    end_time_raw = vote.get("end_time")
    if not end_time_raw:
        return True

    try:
        end_time = datetime.fromisoformat(str(end_time_raw))
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time, timezone.get_current_timezone())
    except ValueError:
        return True

    return end_time > timezone.now()

