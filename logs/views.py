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


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content_items = [self._serialize_content(item, request) for item in Content.objects.filter(owner=request.user)]
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
                    "blockchain": item.get("blockchain"),
                    "download_url": item.get("download_url"),
                }
                for item in merged
            ]
        )

    def _serialize_content(self, content: Content, request):
        serialized = ContentSerializer(content, context={"request": request}).data
        vote = (content.blockchain or {}).get("vote") or {}
        minted = (content.blockchain or {}).get("minted")
        token_id = (content.blockchain or {}).get("token_id")
        fallback_cosine, fallback_phash = _extract_metric_fallback(content.reason)
        top_cosine = content.top_cosine if content.top_cosine is not None else fallback_cosine
        top_phash = content.top_phash_dist if content.top_phash_dist is not None else fallback_phash

        if content.decision == "allow":
            summary = (
                f"워터마크 삽입 완료 (토큰 #{token_id})"
                if minted and token_id
                else "등록 승인 완료"
            )
            extra = (
                f"{(content.blockchain or {}).get('network_name', 'Sepolia')} · Token #{token_id}"
                if token_id
                else "등록 승인됨"
            )
        elif content.decision == "review":
            end_time = vote.get("end_time_display") or vote.get("end_time") or "-"
            summary = "종료된 투표" if _is_review_vote_closed(vote) else "투표 진행 중"
            extra = f"마감 {end_time} · 찬성 {vote.get('upvotes', 0)} · 반대 {vote.get('downvotes', 0)}"
        else:
            summary = "유사도 초과로 등록 차단"
            extra = content.reason or "중복 가능성 높음"

        return {
            "id": str(content.public_id),
            "type": content.decision or "block",
            "file_name": content.original_filename,
            "summary": summary,
            "timestamp": _format_datetime(content.created_at),
            "cosine": _format_cosine(top_cosine),
            "phash": _format_phash(top_phash),
            "extra": extra,
            "preview_url": serialized.get("watermark_file_url") or serialized.get("file_url"),
            "download_url": (
                request.build_absolute_uri(
                    reverse("content_watermark_download", kwargs={"public_id": content.public_id})
                )
                if content.decision == "allow" and (content.watermark or {}).get("applied")
                else serialized.get("watermark_file_url") or serialized.get("file_url")
            ),
            "blockchain": content.blockchain or {},
            "sort_key": content.created_at,
        }

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

        merged = sorted(content_items + verify_items, key=lambda item: item["sort_key"], reverse=True)[:3]
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

        if content.decision == "allow":
            description = (
                f"워터마크 삽입 완료 · 토큰 #{token_id}"
                if token_id
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
            description = f"유사도 {cosine}로 등록 차단" if cosine else "유사도 초과로 등록 차단"
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
