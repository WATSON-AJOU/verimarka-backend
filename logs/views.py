from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.urls import reverse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import re

from contents.serializers import ContentSerializer
from contents.models import Content
from contents.views import _build_content_preview_url, _format_review_vote_summary
from contents.services import ContentRegistrationService

from .models import VerificationHistoryLog


def _format_datetime(value):
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%Y.%m.%d %H:%M")


def _format_cosine(value):
    if value is None:
        return "-"
    return f"{value:.4f} ({value * 100:.1f}%)"


def _format_phash(value):
    if value is None:
        return "-"
    return f"Distance {value} / Threshold 8"


def _extract_metric_fallback(reason):
    if not reason:
        return None, None

    cosine_match = re.search(r"cosine\s*=\s*([0-9]*\.?[0-9]+)", reason, re.IGNORECASE)
    phash_match = re.search(r"phash\s*=\s*([0-9]+)", reason, re.IGNORECASE)

    cosine = float(cosine_match.group(1)) if cosine_match else None
    phash = int(phash_match.group(1)) if phash_match else None
    return cosine, phash


def _is_exact_duplicate_block(content: Content) -> bool:
    reason = (content.reason or "").strip()
    return reason.startswith("동일한 원본 이미지가 이미 처리되었습니다.")


def _content_image_urls(content: Content, request) -> tuple[str | None, str | None]:
    serialized = ContentSerializer(content, context={"request": request}).data
    original_preview_url = serialized.get("file_url") or _build_content_preview_url(request, content)
    watermark_preview_url = serialized.get("watermark_file_url")
    if not original_preview_url and watermark_preview_url:
        original_preview_url = watermark_preview_url
    if not watermark_preview_url and (content.watermark or {}).get("applied"):
        watermark_preview_url = original_preview_url
    return original_preview_url, watermark_preview_url


def _resolve_history_candidate(content: Content, request) -> tuple[str | None, str, str, str]:
    candidate = content.top_match or ((content.candidates or [None])[0] or {})
    comparison_preview_url = candidate.get("preview_url")
    comparison_file_name = candidate.get("db_file") or candidate.get("file_name") or "-"
    comparison_public_id = candidate.get("public_id") or ""
    comparison_db_key = candidate.get("db_key") or ""

    if not comparison_preview_url and comparison_public_id:
        candidate_content = Content.objects.filter(public_id=comparison_public_id).first()
        if candidate_content:
            comparison_public_id = str(candidate_content.public_id)
            comparison_file_name = (
                comparison_file_name if comparison_file_name != "-" else candidate_content.original_filename
            )
            comparison_preview_url, _ = _content_image_urls(candidate_content, request)

    if not comparison_preview_url and comparison_db_key:
        candidate_content = ContentRegistrationService._find_content_by_db_key(comparison_db_key)
        if candidate_content:
            comparison_public_id = comparison_public_id or str(candidate_content.public_id)
            comparison_file_name = (
                comparison_file_name if comparison_file_name != "-" else candidate_content.original_filename
            )
            comparison_preview_url, _ = _content_image_urls(candidate_content, request)

    if not comparison_preview_url and comparison_file_name and comparison_file_name != "-":
        candidate_content = (
            Content.objects.filter(original_filename=comparison_file_name)
            .exclude(pk=content.pk)
            .order_by("-created_at")
            .first()
        )
        if candidate_content:
            comparison_public_id = comparison_public_id or str(candidate_content.public_id)
            comparison_preview_url, _ = _content_image_urls(candidate_content, request)

    return comparison_preview_url, comparison_file_name, comparison_public_id, candidate.get("summary") or ""


def _is_review_vote_closed(vote):
    if not vote:
        return False

    status = (vote.get("status") or "").strip()
    if status and status != "Pending":
        return True

    end_time = vote.get("end_time")
    if not end_time:
        return False

    if isinstance(end_time, str):
        parsed = parse_datetime(end_time)
        if parsed is None:
            return False
        end_time = parsed

    if timezone.is_naive(end_time):
        end_time = timezone.make_aware(end_time, timezone.get_current_timezone())

    return end_time <= timezone.now()


def _is_rejected_review_vote_result(content: Content) -> bool:
    blockchain = content.blockchain or {}
    vote = blockchain.get("vote") or {}
    return blockchain.get("mint_kind") == "review_vote" and (vote.get("status") or "").strip() == "Rejected"


def _has_content_mint(blockchain: dict | None) -> bool:
    if not blockchain:
        return False
    return bool(blockchain.get("minted")) and blockchain.get("mint_kind") == "content"


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content_items = []
        for item in Content.objects.filter(owner=request.user):
            content_items.extend(self._serialize_content(item, request))
        verify_items = [self._serialize_verification(item) for item in VerificationHistoryLog.objects.filter(user=request.user)]

        merged = sorted(
            content_items + verify_items,
            key=lambda item: item["sort_key"],
            reverse=True,
        )

        return Response(
            [
                {
                    "id": item["id"],
                    "type": item["type"],
                    "file_name": item["file_name"],
                    "summary": item["summary"],
                    "timestamp": item["timestamp"],
                    "cosine": item["cosine"],
                    "phash": item["phash"],
                    "extra": item["extra"],
                    "preview_url": item["preview_url"],
                    "original_preview_url": item.get("original_preview_url"),
                    "comparison_preview_url": item.get("comparison_preview_url"),
                    "comparison_file_name": item.get("comparison_file_name"),
                    "comparison_public_id": item.get("comparison_public_id"),
                    "comparison_label": item.get("comparison_label"),
                    "blockchain": item.get("blockchain"),
                    "download_url": item.get("download_url"),
                }
                for item in merged
            ]
        )

    def _serialize_content(self, content: Content, request):
        blockchain = content.blockchain or {}
        vote = blockchain.get("vote") or {}
        minted = _has_content_mint(blockchain)
        token_id = blockchain.get("token_id")
        watermark_applied = bool((content.watermark or {}).get("applied"))
        fallback_cosine, fallback_phash = _extract_metric_fallback(content.reason)
        top_cosine = content.top_cosine if content.top_cosine is not None else fallback_cosine
        top_phash = content.top_phash_dist if content.top_phash_dist is not None else fallback_phash
        original_preview_url, watermark_preview_url = _content_image_urls(content, request)
        comparison_preview_url = None
        comparison_file_name = ""
        comparison_public_id = ""
        comparison_label = ""
        vote_status = (vote.get("status") or "").strip()
        is_review_vote = blockchain.get("mint_kind") == "review_vote"
        review_result_item = None

        if _is_rejected_review_vote_result(content):
            end_time = vote.get("end_time_display") or vote.get("end_time") or "-"
            summary = "투표 종료 · 반대 우세"
            extra = f"마감 {end_time} · 찬성 {vote.get('upvotes', 0)} · 반대 {vote.get('downvotes', 0)}"
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = _resolve_history_candidate(content, request)
            comparison_label = "유사 후보"
            return [
                {
                    "id": str(content.public_id),
                    "type": "review",
                    "file_name": content.original_filename,
                    "summary": summary,
                    "timestamp": _format_datetime(content.created_at),
                    "cosine": _format_cosine(top_cosine),
                    "phash": _format_phash(top_phash),
                    "extra": extra,
                    "preview_url": watermark_preview_url or original_preview_url,
                    "original_preview_url": original_preview_url,
                    "comparison_preview_url": comparison_preview_url,
                    "comparison_file_name": comparison_file_name,
                    "comparison_public_id": comparison_public_id,
                    "comparison_label": comparison_label,
                    "download_url": None,
                    "blockchain": blockchain,
                    "sort_key": content.created_at,
                }
            ]
        elif is_review_vote and vote_status == "Approved":
            end_time = vote.get("end_time_display") or vote.get("end_time") or "-"
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = _resolve_history_candidate(content, request)
            comparison_label = "유사 후보"
            review_result_item = {
                "id": f"{content.public_id}-review-result",
                "type": "review",
                "file_name": content.original_filename,
                "summary": "투표 종료 · 찬성 우세",
                "timestamp": _format_datetime(content.created_at),
                "cosine": _format_cosine(top_cosine),
                "phash": _format_phash(top_phash),
                "extra": f"마감 {end_time} · 찬성 {vote.get('upvotes', 0)} · 반대 {vote.get('downvotes', 0)}",
                "preview_url": watermark_preview_url or original_preview_url,
                "original_preview_url": original_preview_url,
                "comparison_preview_url": comparison_preview_url,
                "comparison_file_name": comparison_file_name,
                "comparison_public_id": comparison_public_id,
                "comparison_label": comparison_label,
                "download_url": None,
                "blockchain": blockchain,
                "sort_key": content.created_at,
            }
        elif content.decision == "allow":
            summary = (
                f"워터마크 삽입 완료 (토큰 #{token_id})"
                if minted and token_id
                else "워터마크 삽입 완료"
                if watermark_applied
                else "등록 승인 완료"
            )
            extra = (
                f"{blockchain.get('network_name', 'Sepolia')} · Token #{token_id}"
                if minted and token_id
                else "토큰 발행 대기"
                if watermark_applied
                else "등록 승인됨"
            )
            comparison_preview_url = watermark_preview_url
            comparison_file_name = ""
            comparison_label = "워터마크 삽입본"
        elif content.decision == "review":
            end_time = vote.get("end_time_display") or vote.get("end_time") or "-"
            summary = "종료된 투표" if _is_review_vote_closed(vote) else "투표 진행 중"
            extra = f"마감 {end_time} · 찬성 {vote.get('upvotes', 0)} · 반대 {vote.get('downvotes', 0)}"
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = _resolve_history_candidate(content, request)
            comparison_label = "유사 후보"
        else:
            summary = (
                "동일한 저작물 재업로드로 차단"
                if _is_exact_duplicate_block(content)
                else "유사도 초과로 등록 차단"
            )
            extra = content.reason or "중복 가능성 높음"
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = _resolve_history_candidate(content, request)
            comparison_label = "유사 후보"

        allow_or_block_item = {
            "id": str(content.public_id),
            "type": content.decision or "block",
            "file_name": content.original_filename,
            "summary": summary,
            "timestamp": _format_datetime(content.created_at),
            "cosine": _format_cosine(top_cosine),
            "phash": _format_phash(top_phash),
            "extra": extra,
            "preview_url": watermark_preview_url or original_preview_url,
            "original_preview_url": original_preview_url,
            "comparison_preview_url": comparison_preview_url,
            "comparison_file_name": comparison_file_name,
            "comparison_public_id": comparison_public_id,
            "comparison_label": comparison_label,
            "download_url": (
                reverse("content_watermark_download", kwargs={"public_id": content.public_id})
                if content.decision == "allow" and watermark_applied
                else None
            ),
            "blockchain": blockchain,
            "sort_key": content.created_at,
        }
        return [allow_or_block_item, review_result_item] if review_result_item else [allow_or_block_item]

    def _serialize_verification(self, log: VerificationHistoryLog):
        candidate = log.candidate or {}
        blockchain = log.blockchain or {}
        detect = log.detect or {}
        return {
            "id": f"verify-{log.id}",
            "type": "verify",
            "file_name": log.uploaded_file_name,
            "summary": log.summary or (
                f"워터마크 검증 성공 · Token #{blockchain.get('token_id')}"
                if log.outcome == "verified"
                else "검증 실패 · 유사 후보 탐색 완료"
            ),
            "timestamp": _format_datetime(log.created_at),
            "cosine": _format_cosine(candidate.get("cosine")),
            "phash": _format_phash(candidate.get("phash_dist")),
            "extra": (
                f"{blockchain.get('network_name', 'Sepolia')} · Verified"
                if log.outcome == "verified"
                else candidate.get("summary") or detect.get("status_label") or "검증 완료"
            ),
            "preview_url": candidate.get("preview_url") or log.uploaded_preview_url,
            "download_url": candidate.get("preview_url") or log.uploaded_preview_url,
            "blockchain": blockchain,
            "sort_key": log.created_at,
        }


class PublicRecentActivityView(APIView):
    permission_classes = []

    def get(self, request):
        content_items = [self._serialize_content(item, request) for item in Content.objects.select_related("owner").all()[:100]]
        verify_items = [self._serialize_verification(item) for item in VerificationHistoryLog.objects.select_related("user").all()[:100]]

        merged = sorted(content_items + verify_items, key=lambda item: item["sort_key"], reverse=True)[:6]
        return Response(
            [
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "status": item["status"],
                    "title": item["title"],
                    "description": item["description"],
                    "extra": item.get("extra"),
                    "progress": item["progress"],
                    "tone": item["tone"],
                    "preview_url": item["preview_url"],
                    "blockchain": item.get("blockchain"),
                }
                for item in merged
            ]
        )

    def _serialize_content(self, content: Content, request):
        vote = (content.blockchain or {}).get("vote") or {}
        token_id = (content.blockchain or {}).get("token_id")
        watermark_applied = bool((content.watermark or {}).get("applied"))
        minted = _has_content_mint(content.blockchain or {})

        if content.decision == "allow":
            description = (
                f"워터마크 삽입 완료 · 토큰 #{token_id}"
                if minted and token_id
                else "워터마크 삽입 완료"
                if watermark_applied
                else "등록 승인 완료"
            )
            progress = None
            status = "ALLOW"
            tone = "allow"
        elif content.decision == "review":
            description = _format_review_vote_summary(content)
            progress = None
            total = int(vote.get("upvotes", 0)) + int(vote.get("downvotes", 0))
            if total > 0:
                progress = round((int(vote.get("upvotes", 0)) / total) * 100)
            status = "REVIEW"
            tone = "review"
        else:
            cosine = f"{content.top_cosine * 100:.1f}%" if content.top_cosine is not None else None
            description = (
                "동일한 저작물 재업로드로 차단"
                if _is_exact_duplicate_block(content)
                else (f"유사도 {cosine}로 등록 차단" if cosine else "유사도 초과로 등록 차단")
            )
            progress = None
            status = "BLOCK"
            tone = "block"

        return {
            "id": str(content.public_id),
            "type": content.decision or "block",
            "status": status,
            "title": content.original_filename,
            "description": description,
            "extra": (
                f"마감 {vote.get('end_time_display') or vote.get('end_time') or '-'} · 찬성 {vote.get('upvotes', 0)} · 반대 {vote.get('downvotes', 0)}"
                if content.decision == "review"
                else content.reason or ""
            ),
            "progress": progress,
            "tone": tone,
            "preview_url": _build_content_preview_url(request, content),
            "blockchain": content.blockchain or {},
            "sort_key": content.created_at,
        }

    def _serialize_verification(self, log: VerificationHistoryLog):
        candidate = log.candidate or {}
        detect = log.detect or {}
        if log.outcome == "verified":
            description = f"검증 성공 · Token #{(log.blockchain or {}).get('token_id', '-')}"
        else:
            description = candidate.get("summary") or detect.get("status_label") or "검증 실패 · 유사 후보 탐색 완료"
        return {
            "id": f"verify-{log.id}",
            "type": "verify",
            "status": "VERIFY",
            "title": log.uploaded_file_name,
            "description": description,
            "extra": candidate.get("summary") or detect.get("status_label") or "",
            "progress": None,
            "tone": "verify",
            "preview_url": candidate.get("preview_url") or log.uploaded_preview_url,
            "blockchain": log.blockchain or {},
            "sort_key": log.created_at,
        }
