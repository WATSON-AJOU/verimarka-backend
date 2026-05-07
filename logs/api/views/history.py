from django.urls import reverse
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.api.utils import build_content_preview_url, format_review_vote_summary
from contents.models import Content
from logs.api.utils import (
    content_image_urls,
    extract_metric_fallback,
    format_cosine,
    format_datetime,
    format_phash,
    has_content_mint,
    is_exact_duplicate_block,
    is_rejected_review_vote_result,
    resolve_history_candidate,
)
from logs.models import VerificationHistoryLog


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content_items = []
        for item in Content.objects.filter(owner=request.user):
            content_items.extend(self._serialize_content(item, request))
        verify_items = [
            self._serialize_verification(item)
            for item in VerificationHistoryLog.objects.filter(user=request.user)
        ]
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
        minted = has_content_mint(blockchain)
        token_id = blockchain.get("token_id")
        watermark_applied = bool((content.watermark or {}).get("applied"))
        fallback_cosine, fallback_phash = extract_metric_fallback(content.reason)
        top_cosine = (
            content.top_cosine if content.top_cosine is not None else fallback_cosine
        )
        top_phash = (
            content.top_phash_dist
            if content.top_phash_dist is not None
            else fallback_phash
        )
        original_preview_url, watermark_preview_url = content_image_urls(
            content, request
        )
        comparison_preview_url = None
        comparison_file_name = ""
        comparison_public_id = ""
        comparison_label = ""
        vote_status = (vote.get("status") or "").strip()
        has_review_vote = (
            bool(vote_status) or blockchain.get("mint_kind") == "review_vote"
        )
        review_result_item = None

        if is_rejected_review_vote_result(content):
            end_time = vote.get("end_time_display") or vote.get("end_time") or "-"
            summary = "투표 종료 · 반대 우세"
            extra = (
                f"마감 {end_time} · 찬성 {vote.get('upvotes', 0)} "
                f"· 반대 {vote.get('downvotes', 0)}"
            )
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = (
                resolve_history_candidate(content, request)
            )
            comparison_label = "유사 후보"
            return [
                {
                    "id": str(content.public_id),
                    "type": "review",
                    "file_name": content.original_filename,
                    "summary": summary,
                    "timestamp": format_datetime(content.created_at),
                    "cosine": format_cosine(top_cosine),
                    "phash": format_phash(top_phash),
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
        if has_review_vote and vote_status == "Approved":
            end_time = vote.get("end_time_display") or vote.get("end_time") or "-"
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = (
                resolve_history_candidate(content, request)
            )
            comparison_label = "유사 후보"
            review_result_item = {
                "id": f"{content.public_id}-review-result",
                "type": "review",
                "file_name": content.original_filename,
                "summary": "투표 종료 · 찬성 우세",
                "timestamp": format_datetime(content.created_at),
                "cosine": format_cosine(top_cosine),
                "phash": format_phash(top_phash),
                "extra": (
                    f"마감 {end_time} · 찬성 {vote.get('upvotes', 0)} "
                    f"· 반대 {vote.get('downvotes', 0)}"
                ),
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
        if content.decision == "allow":
            summary = (
                f"워터마크 & 토큰 발급 완료 (토큰 #{token_id})"
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
            comparison_file_name = content.original_filename
            comparison_public_id = str(content.public_id)
            comparison_label = "워터마크 결과"
            item = {
                "id": str(content.public_id),
                "type": "allow",
                "file_name": content.original_filename,
                "summary": summary,
                "timestamp": format_datetime(content.created_at),
                "cosine": format_cosine(top_cosine),
                "phash": format_phash(top_phash),
                "extra": extra,
                "preview_url": watermark_preview_url or original_preview_url,
                "original_preview_url": original_preview_url,
                "comparison_preview_url": comparison_preview_url,
                "comparison_file_name": comparison_file_name,
                "comparison_public_id": comparison_public_id,
                "comparison_label": comparison_label,
                "download_url": reverse(
                    "content_watermark_download",
                    kwargs={"public_id": content.public_id},
                )
                if watermark_applied
                else None,
                "blockchain": blockchain,
                "sort_key": content.created_at,
            }
            return [review_result_item, item] if review_result_item else [item]
        elif content.decision == "review":
            summary = format_review_vote_summary(content)
            extra = (
                f"찬성 {vote.get('upvotes', 0)} · 반대 {vote.get('downvotes', 0)}"
                if vote
                else "커뮤니티 검증 필요"
            )
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = (
                resolve_history_candidate(content, request)
            )
            comparison_label = "유사 후보"
        else:
            summary = (
                "동일한 저작물 재업로드로 차단"
                if is_exact_duplicate_block(content)
                else "등록 차단"
            )
            extra = content.reason or "유사 콘텐츠로 차단됨"
            comparison_preview_url, comparison_file_name, comparison_public_id, _ = (
                resolve_history_candidate(content, request)
            )
            comparison_label = "유사 후보"

        item = {
            "id": str(content.public_id),
            "type": content.decision or "block",
            "file_name": content.original_filename,
            "summary": summary,
            "timestamp": format_datetime(content.created_at),
            "cosine": format_cosine(top_cosine),
            "phash": format_phash(top_phash),
            "extra": extra,
            "preview_url": original_preview_url,
            "original_preview_url": original_preview_url,
            "comparison_preview_url": comparison_preview_url,
            "comparison_file_name": comparison_file_name,
            "comparison_public_id": comparison_public_id,
            "comparison_label": comparison_label,
            "download_url": None,
            "blockchain": blockchain,
            "sort_key": content.created_at,
        }
        return [review_result_item, item] if review_result_item else [item]

    def _serialize_verification(self, item: VerificationHistoryLog):
        return {
            "id": str(item.id),
            "type": "verify",
            "file_name": item.uploaded_file_name,
            "summary": item.summary
            or ("워터마크 검증 성공" if item.outcome == "verified" else "검증 실패"),
            "timestamp": format_datetime(item.created_at),
            "cosine": format_cosine((item.candidate or {}).get("cosine")),
            "phash": format_phash((item.candidate or {}).get("phash_dist")),
            "extra": (item.candidate or {}).get("summary")
            or ((item.blockchain or {}).get("verification_link") or "-"),
            "preview_url": item.uploaded_preview_url,
            "original_preview_url": item.uploaded_preview_url,
            "comparison_preview_url": (item.candidate or {}).get("preview_url"),
            "comparison_file_name": (item.candidate or {}).get("file_name"),
            "comparison_public_id": None,
            "comparison_label": "유사 후보"
            if (item.candidate or {}).get("preview_url")
            else "",
            "download_url": None,
            "blockchain": item.blockchain,
            "sort_key": item.created_at,
        }


class PublicRecentActivityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        payload = []
        for content in Content.objects.exclude(status="pending").order_by(
            "-updated_at"
        )[:12]:
            blockchain = content.blockchain or {}
            payload.append(
                {
                    "id": str(content.public_id),
                    "type": content.decision or content.status,
                    "status": (content.decision or content.status).upper(),
                    "title": content.original_filename,
                    "description": content.reason or "",
                    "extra": blockchain.get("network_name") or "",
                    "progress": None,
                    "tone": content.decision or content.status,
                    "preview_url": build_content_preview_url(request, content),
                    "blockchain": blockchain,
                }
            )
        return Response(payload)
