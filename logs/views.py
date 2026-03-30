from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import re

from contents.serializers import ContentSerializer
from contents.models import Content

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
            summary = f"투표 진행 중 · {vote.get('status', 'Pending')}"
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
            "sort_key": log.created_at,
        }
