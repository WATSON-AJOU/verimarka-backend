import re

from django.utils import timezone

from contents.api.serializers import ContentSerializer
from contents.api.utils import build_content_preview_url
from contents.models import Content
from contents.api.services import ContentRegistrationService


def format_datetime(value):
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%Y.%m.%d %H:%M")


def format_cosine(value):
    if value is None:
        return "-"
    return f"{value:.4f} ({value * 100:.1f}%)"


def format_phash(value):
    if value is None:
        return "-"
    return f"Distance {value} / Threshold 8"


def extract_metric_fallback(reason):
    if not reason:
        return None, None
    cosine_match = re.search(r"cosine\s*=\s*([0-9]*\.?[0-9]+)", reason, re.IGNORECASE)
    phash_match = re.search(r"phash\s*=\s*([0-9]+)", reason, re.IGNORECASE)
    cosine = float(cosine_match.group(1)) if cosine_match else None
    phash = int(phash_match.group(1)) if phash_match else None
    return cosine, phash


def is_exact_duplicate_block(content: Content) -> bool:
    reason = (content.reason or "").strip()
    return reason.startswith("동일한 원본 이미지가 이미 처리되었습니다.")


def content_image_urls(content: Content, request) -> tuple[str | None, str | None]:
    serialized = ContentSerializer(content, context={"request": request}).data
    original_preview_url = serialized.get("file_url") or build_content_preview_url(request, content)
    watermark_preview_url = serialized.get("watermark_file_url")
    if not original_preview_url and watermark_preview_url:
        original_preview_url = watermark_preview_url
    if not watermark_preview_url and (content.watermark or {}).get("applied"):
        watermark_preview_url = original_preview_url
    return original_preview_url, watermark_preview_url


def resolve_history_candidate(content: Content, request) -> tuple[str | None, str, str, str]:
    candidate = content.top_match or ((content.candidates or [None])[0] or {})
    comparison_preview_url = candidate.get("preview_url")
    comparison_file_name = candidate.get("db_file") or candidate.get("file_name") or "-"
    comparison_public_id = candidate.get("public_id") or ""
    comparison_db_key = candidate.get("db_key") or ""

    if not comparison_preview_url and comparison_public_id:
        candidate_content = Content.objects.filter(public_id=comparison_public_id).first()
        if candidate_content:
            comparison_public_id = str(candidate_content.public_id)
            if comparison_file_name == "-":
                comparison_file_name = candidate_content.original_filename
            comparison_preview_url, _ = content_image_urls(candidate_content, request)

    if not comparison_preview_url and comparison_db_key:
        candidate_content = ContentRegistrationService._find_content_by_db_key(comparison_db_key)
        if candidate_content:
            comparison_public_id = comparison_public_id or str(candidate_content.public_id)
            if comparison_file_name == "-":
                comparison_file_name = candidate_content.original_filename
            comparison_preview_url, _ = content_image_urls(candidate_content, request)

    if not comparison_preview_url and comparison_file_name and comparison_file_name != "-":
        candidate_content = (
            Content.objects.filter(original_filename=comparison_file_name)
            .exclude(pk=content.pk)
            .order_by("-created_at")
            .first()
        )
        if candidate_content:
            comparison_public_id = comparison_public_id or str(candidate_content.public_id)
            comparison_preview_url, _ = content_image_urls(candidate_content, request)

    return comparison_preview_url, comparison_file_name, comparison_public_id, candidate.get("summary") or ""


def is_rejected_review_vote_result(content: Content) -> bool:
    blockchain = content.blockchain or {}
    vote = blockchain.get("vote") or {}
    return blockchain.get("mint_kind") == "review_vote" and (vote.get("status") or "").strip() == "Rejected"


def has_content_mint(blockchain: dict | None) -> bool:
    if not blockchain:
        return False
    return bool(blockchain.get("minted")) and blockchain.get("mint_kind") == "content"
