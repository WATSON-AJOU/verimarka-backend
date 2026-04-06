from datetime import datetime, timedelta
from math import ceil

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from web3 import Web3

from analysis.models import AIJob
from contents.blockchain_service import ContentBlockchainService
from contents.models import Content
from contents.serializers import ContentSerializer
from contents.services import ContentRegistrationService
from contents.views import _build_content_preview_url
from logs.models import VerificationHistoryLog
from ..models import User
from ..serializers import (
    AdminDashboardSerializer,
    AdminImageDetailSerializer,
    AdminImageListSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserUpdateSerializer,
    AdminVoteDetailSerializer,
    AdminVoteListSerializer,
)


def _format_dt(value) -> str:
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


def _format_date(value) -> str:
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%Y-%m-%d")


def _role_label(user: User) -> str:
    return "관리자" if user.is_staff or user.is_superuser else "일반회원"


def _verification_label(user: User) -> str:
    return "완료" if user.phone_verified or user.email_verified else "미인증"


def _account_status_label(user: User) -> str:
    return "정상" if user.is_active and not user.is_deleted else "정지"


def _user_nft_count(user: User) -> int | None:
    wallet_link = getattr(user, "wallet_link", None)
    if not wallet_link or not wallet_link.address:
        return None
    try:
        blockchain = ContentBlockchainService._create_client()
        return int(blockchain.contract.functions.balanceOf(Web3.to_checksum_address(wallet_link.address)).call())
    except Exception:
        return None


def _user_vote_permission(user: User) -> str:
    nft_count = _user_nft_count(user)
    return "활성" if nft_count is not None and nft_count >= 3 else "비활성"


def _image_decision_label(content: Content) -> str:
    value = (content.decision or content.status or "").upper()
    return value or "PENDING"


def _vote_status_label(content: Content) -> str:
    vote = (content.blockchain or {}).get("vote") or {}
    if not vote:
        return "없음"
    end_at = _vote_end_datetime(content)
    if end_at is not None and timezone.now() >= end_at:
        return "종료"
    return "진행중" if vote.get("status") == "Pending" else "종료"


def _vote_decision_label(content: Content) -> str:
    vote = (content.blockchain or {}).get("vote") or {}
    status_name = (vote.get("status") or "").strip()
    if status_name == "Approved":
        return "등록 가능"
    if status_name == "Rejected":
        return "등록 거절"
    return "미정"


def _vote_started_label(content: Content) -> str:
    vote = (content.blockchain or {}).get("vote") or {}
    return vote.get("started_at_display") or vote.get("started_at") or "-"


def _vote_end_label(content: Content) -> str:
    vote = (content.blockchain or {}).get("vote") or {}
    return vote.get("end_time_display") or vote.get("end_time") or "-"


def _vote_end_date(content: Content):
    end_at = _vote_end_datetime(content)
    if not end_at:
        return None
    return timezone.localtime(end_at).date()


def _vote_end_datetime(content: Content):
    vote = (content.blockchain or {}).get("vote") or {}
    raw = vote.get("end_time")
    if not raw:
        return None
    if isinstance(raw, datetime):
        parsed = raw
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    if isinstance(raw, str):
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    return None


def _vote_rates(content: Content) -> tuple[float, float]:
    vote = (content.blockchain or {}).get("vote") or {}
    upvotes = int(vote.get("upvotes") or 0)
    downvotes = int(vote.get("downvotes") or 0)
    total = upvotes + downvotes
    if total <= 0:
        return 0.0, 0.0
    return round((upvotes / total) * 100, 1), round((downvotes / total) * 100, 1)


def _content_preview_urls(content: Content, request) -> tuple[str | None, str | None]:
    serializer = ContentSerializer(content, context={"request": request})
    data = serializer.data
    original_preview_url = data.get("file_url") or _build_content_preview_url(request, content)
    watermark_preview_url = data.get("watermark_file_url")

    # Older rows can miss one side of the image URL pair; fall back so the UI
    # still renders an actual image instead of an empty placeholder.
    if not original_preview_url and watermark_preview_url:
        original_preview_url = watermark_preview_url
    if not watermark_preview_url and (content.watermark or {}).get("applied"):
        watermark_preview_url = original_preview_url

    return original_preview_url, watermark_preview_url


def _serialize_user_list_item(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email or "",
        "nickname": user.display_name or user.nickname or user.username,
        "role": _role_label(user),
        "verification": _verification_label(user),
        "nft_count": _user_nft_count(user),
        "joined_at": _format_dt(user.date_joined),
        "last_login": _format_dt(user.last_login),
        "status": _account_status_label(user),
    }


def _serialize_recent_content_activity(content: Content, request) -> list[dict]:
    preview_url, _ = _content_preview_urls(content, request)
    activities = [
        {
            "title": content.original_filename,
            "result": _image_decision_label(content),
            "date": _format_dt(content.created_at),
            "preview_url": preview_url,
            "image_public_id": str(content.public_id),
            "detail_path": f"/images/{content.public_id}",
            "detail_label": "이미지 상세",
            "meta": "저작물 등록",
            "sort_key": content.created_at,
        }
    ]
    blockchain = content.blockchain or {}
    if blockchain.get("minted") and blockchain.get("mint_kind") == "content":
        minted_at_display = blockchain.get("minted_at")
        minted_at = None
        if isinstance(minted_at_display, str):
            normalized = minted_at_display.replace("Z", "+00:00")
            try:
                minted_at = datetime.fromisoformat(normalized)
            except ValueError:
                minted_at = None
        if minted_at and timezone.is_naive(minted_at):
            minted_at = timezone.make_aware(minted_at, timezone.get_current_timezone())
        sort_key = minted_at or content.updated_at
        activities.append(
            {
                "title": content.original_filename,
                "result": "MINTED",
                "date": _format_dt(sort_key),
                "preview_url": preview_url,
                "image_public_id": str(content.public_id),
                "detail_path": f"/images/{content.public_id}",
                "detail_label": "이미지 상세",
                "meta": f"토큰 발행 · #{blockchain.get('token_id') or '-'}",
                "sort_key": sort_key,
            }
        )
    return activities


def _serialize_recent_verification_activity(log: VerificationHistoryLog) -> dict:
    candidate = log.candidate or {}
    return {
        "title": log.uploaded_file_name,
        "result": "VERIFY" if log.outcome == "verified" else "CANDIDATE",
        "date": _format_dt(log.created_at),
        "preview_url": log.uploaded_preview_url or candidate.get("preview_url"),
        "image_public_id": candidate.get("public_id") or "",
        "detail_path": f"/images/{candidate.get('public_id')}" if candidate.get("public_id") else "",
        "detail_label": "이미지 상세" if candidate.get("public_id") else "",
        "meta": log.summary or ("워터마크 검증 성공" if log.outcome == "verified" else "유사 후보 탐색"),
        "sort_key": log.created_at,
    }


def _serialize_recent_vote_activity(item, request) -> dict:
    preview_url, _ = _content_preview_urls(item.content, request)
    return {
        "title": item.content.original_filename,
        "result": "VOTE",
        "date": _format_dt(item.created_at),
        "preview_url": preview_url,
        "image_public_id": str(item.content.public_id),
        "detail_path": f"/votes/{item.content.public_id}",
        "detail_label": "투표 상세",
        "meta": f"커뮤니티 투표 {'찬성' if item.choice == 'yes' else '반대'} 참여",
        "sort_key": item.created_at,
    }


def _serialize_user_detail(user: User, request, activity_page: int = 1, activity_page_size: int = 10) -> dict:
    wallet_link = getattr(user, "wallet_link", None)
    contents = list(user.contents.order_by("-created_at"))
    verification_logs = list(user.verification_history_logs.all())
    vote_logs = list(user.vote_participations.select_related("content").all())
    all_recent_activities = []
    for content in contents:
        all_recent_activities.extend(_serialize_recent_content_activity(content, request))
    all_recent_activities.extend(_serialize_recent_verification_activity(log) for log in verification_logs)
    all_recent_activities.extend(_serialize_recent_vote_activity(item, request) for item in vote_logs)
    all_recent_activities = sorted(all_recent_activities, key=lambda item: item["sort_key"], reverse=True)
    total_count = len(all_recent_activities)
    total_pages = max(1, ceil(total_count / activity_page_size)) if activity_page_size > 0 else 1
    safe_page = min(max(activity_page, 1), total_pages)
    start = (safe_page - 1) * activity_page_size
    end = start + activity_page_size
    recent_activities = all_recent_activities[start:end]
    return {
        **_serialize_user_list_item(user),
        "recent_ip": user.last_login_ip or "",
        "sms_verification": "완료" if user.phone_verified else "미인증",
        "email_verification": "완료" if user.email_verified else "미인증",
        "wallet_address": wallet_link.address if wallet_link else "",
        "wallet_method": wallet_link.wallet_type if wallet_link else "",
        "wallet_linked_at": _format_date(wallet_link.verified_at) if wallet_link else "",
        "vote_permission": _user_vote_permission(user),
        "activity_page": safe_page,
        "activity_page_size": activity_page_size,
        "activity_total_count": total_count,
        "activity_total_pages": total_pages,
        "recent_activities": [
            {
                "title": item["title"],
                "result": item["result"],
                "date": item["date"],
                "preview_url": item["preview_url"],
                "image_public_id": item["image_public_id"],
                "detail_path": item["detail_path"],
                "detail_label": item["detail_label"],
                "meta": item["meta"],
            }
            for item in recent_activities
        ],
    }


def _serialize_image_list_item(content: Content, request) -> dict:
    preview_url, _ = _content_preview_urls(content, request)
    return {
        "public_id": str(content.public_id),
        "file_name": content.original_filename,
        "uploader_email": content.owner.email or content.owner.username,
        "uploaded_at": _format_date(content.created_at),
        "decision": _image_decision_label(content),
        "vote_status": _vote_status_label(content),
        "preview_url": preview_url,
    }


def _serialize_image_detail(content: Content, request) -> dict:
    preview_url, watermark_preview_url = _content_preview_urls(content, request)
    blockchain = content.blockchain or {}
    vote = blockchain.get("vote") or {}
    candidate = content.top_match or ((content.candidates or [None])[0] or {})
    comparison_preview_url = watermark_preview_url
    comparison_label = "워터마크 결과"
    comparison_file_name = content.original_filename
    comparison_public_id = ""
    if _image_decision_label(content) in {"BLOCK", "REVIEW"}:
        comparison_preview_url = candidate.get("preview_url")
        comparison_label = "유사 후보"
        comparison_db_key = candidate.get("db_key") or ""
        comparison_file_name = candidate.get("db_file") or candidate.get("file_name") or "-"
        comparison_public_id = candidate.get("public_id") or ""
        if not comparison_preview_url and comparison_public_id:
            candidate_content = Content.objects.filter(public_id=comparison_public_id).first()
            if candidate_content:
                comparison_preview_url, _ = _content_preview_urls(candidate_content, request)
        if not comparison_preview_url and comparison_db_key:
            candidate_content = ContentRegistrationService._find_content_by_db_key(comparison_db_key)
            if candidate_content:
                comparison_public_id = comparison_public_id or str(candidate_content.public_id)
                comparison_file_name = comparison_file_name if comparison_file_name != "-" else candidate_content.original_filename
                comparison_preview_url, _ = _content_preview_urls(candidate_content, request)
        if not comparison_preview_url and comparison_file_name and comparison_file_name != "-":
            candidate_content = (
                Content.objects.filter(original_filename=comparison_file_name)
                .exclude(pk=content.pk)
                .order_by("-created_at")
                .first()
            )
            if candidate_content:
                comparison_public_id = comparison_public_id or str(candidate_content.public_id)
                comparison_preview_url, _ = _content_preview_urls(candidate_content, request)
    return {
        "public_id": str(content.public_id),
        "file_name": content.original_filename,
        "uploader_email": content.owner.email or content.owner.username,
        "uploaded_at": _format_date(content.created_at),
        "decision": _image_decision_label(content),
        "preview_url": preview_url,
        "watermark_preview_url": watermark_preview_url,
        "comparison_preview_url": comparison_preview_url,
        "comparison_label": comparison_label,
        "comparison_file_name": comparison_file_name,
        "comparison_public_id": comparison_public_id,
        "embedding_similarity": round(float(content.top_cosine or 0) * 100, 1) if content.top_cosine is not None else None,
        "phash_similarity": float(content.top_phash_dist) if content.top_phash_dist is not None else None,
        "threshold_result": round(float(vote.get("threshold") or 0) * 100, 1) if vote.get("threshold") is not None else None,
        "linked_vote": {
            "vote_id": vote.get("vote_id") or "",
            "status": _vote_status_label(content),
            "yes_rate": _vote_rates(content)[0],
            "no_rate": _vote_rates(content)[1],
            "deadline": _vote_end_label(content),
        } if vote else {},
        "blockchain": {
            "token_id": blockchain.get("token_id") or "",
            "tx_hash": blockchain.get("tx_hash") or blockchain.get("transaction_hash") or "",
            "block_number": blockchain.get("block_number") or "",
            "minted_at": blockchain.get("minted_at_display") or blockchain.get("minted_at") or "",
            "decision": _vote_decision_label(content) if blockchain.get("mint_kind") == "review_vote" else _image_decision_label(content),
        },
    }


def _serialize_vote_list_item(content: Content, request) -> dict:
    vote = (content.blockchain or {}).get("vote") or {}
    yes_rate, no_rate = _vote_rates(content)
    preview_url, _ = _content_preview_urls(content, request)
    return {
        "public_id": str(content.public_id),
        "vote_id": vote.get("vote_id") or f"VOTE-{(content.blockchain or {}).get('token_id') or content.id}",
        "file_name": content.original_filename,
        "uploader_email": content.owner.email or content.owner.username,
        "status": _vote_status_label(content),
        "start_date": _vote_started_label(content),
        "end_date": _vote_end_label(content),
        "yes_rate": yes_rate,
        "no_rate": no_rate,
        "participant_count": int(vote.get("participant_count") or 0),
        "decision": _vote_decision_label(content),
        "preview_url": preview_url,
    }


def _serialize_vote_detail(content: Content, request) -> dict:
    payload = _serialize_vote_list_item(content, request)
    voter_records = []
    for item in content.vote_participations.select_related("user").all():
        voter_records.append(
            {
                "user_id": item.user_id,
                "email": item.user.email or item.user.username,
                "wallet": item.wallet_address,
                "choice": "찬성" if item.choice == "yes" else "반대",
                "nft_count": _user_nft_count(item.user),
                "voted_at": _format_dt(item.created_at),
            }
        )

    return {
        **payload,
        "image_id": str(content.public_id),
        "voter_records": voter_records,
    }


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        today = timezone.localdate()
        today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        review_vote_contents = list(
            Content.objects.filter(blockchain__mint_kind="review_vote").only("blockchain")
        )

        recent_feed = []
        for content in Content.objects.select_related("owner").order_by("-updated_at")[:5]:
            preview_url, _ = _content_preview_urls(content, request)
            recent_feed.append(
                {
                    "date": _format_dt(content.updated_at),
                    "email": content.owner.email or content.owner.username,
                    "title": content.original_filename,
                    "result": _image_decision_label(content),
                    "preview_url": preview_url,
                    "detail_path": f"/images/{content.public_id}",
                }
            )

        payload = {
            "total_users": User.objects.filter(is_deleted=False).count(),
            "verified_users": User.objects.filter(Q(phone_verified=True) | Q(email_verified=True), is_deleted=False).count(),
            "vote_eligible_users": User.objects.filter(is_deleted=False).annotate(
                minted_count=Count(
                    "contents",
                    filter=Q(contents__blockchain__minted=True, contents__blockchain__mint_kind="content"),
                )
            ).filter(minted_count__gte=3).count(),
            "total_images": Content.objects.count(),
            "images_uploaded_today": Content.objects.filter(created_at__gte=today_start, created_at__lt=tomorrow_start).count(),
            "active_votes": sum(
                1
                for content in review_vote_contents
                if ((content.blockchain or {}).get("vote") or {}).get("status") == "Pending"
            ),
            "closing_votes_today": sum(1 for content in review_vote_contents if _vote_end_date(content) == today),
            "pending_jobs": AIJob.objects.filter(status__in=["queued", "running"]).count(),
            "recent_feed": recent_feed,
        }
        return Response(AdminDashboardSerializer(payload).data)


class AdminUserListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = User.objects.select_related("wallet_link").filter(is_deleted=False).order_by("id")
        payload = [_serialize_user_list_item(user) for user in queryset]
        return Response(AdminUserListSerializer(payload, many=True).data)


class AdminUserDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, user_id: int):
        user = get_object_or_404(User.objects.select_related("wallet_link"), pk=user_id)
        try:
            activity_page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            activity_page = 1
        try:
            activity_page_size = int(request.query_params.get("page_size", "10"))
        except ValueError:
            activity_page_size = 10
        activity_page_size = min(max(activity_page_size, 1), 100)
        payload = _serialize_user_detail(user, request, activity_page=activity_page, activity_page_size=activity_page_size)
        return Response(AdminUserDetailSerializer(payload).data)

    def patch(self, request, user_id: int):
        user = get_object_or_404(User.objects.select_related("wallet_link"), pk=user_id)
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.update(user, serializer.validated_data)
        payload = _serialize_user_detail(user, request)
        return Response(AdminUserDetailSerializer(payload).data)


class AdminImageListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = Content.objects.select_related("owner").order_by("-created_at")
        payload = [_serialize_image_list_item(content, request) for content in queryset]
        return Response(AdminImageListSerializer(payload, many=True).data)


class AdminImageDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, public_id):
        content = get_object_or_404(Content.objects.select_related("owner"), public_id=public_id)
        payload = _serialize_image_detail(content, request)
        return Response(AdminImageDetailSerializer(payload).data)


class AdminVoteListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = Content.objects.select_related("owner").filter(blockchain__mint_kind="review_vote").order_by("-updated_at")
        payload = [_serialize_vote_list_item(content, request) for content in queryset]
        return Response(AdminVoteListSerializer(payload, many=True).data)


class AdminVoteDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, public_id):
        content = get_object_or_404(
            Content.objects.select_related("owner").prefetch_related("vote_participations__user"),
            public_id=public_id,
            blockchain__mint_kind="review_vote",
        )
        payload = _serialize_vote_detail(content, request)
        return Response(AdminVoteDetailSerializer(payload).data)
