from datetime import datetime, timedelta

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
from contents.views import _build_content_preview_url
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
    vote = (content.blockchain or {}).get("vote") or {}
    raw = vote.get("end_time")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return timezone.localtime(raw).date()
    if isinstance(raw, str):
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return timezone.localtime(parsed).date()
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
    return _build_content_preview_url(request, content) or data.get("file_url"), data.get("watermark_file_url")


def _serialize_user_list_item(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email or "",
        "nickname": user.nickname or user.username,
        "role": _role_label(user),
        "verification": _verification_label(user),
        "nft_count": _user_nft_count(user),
        "joined_at": _format_dt(user.date_joined),
        "last_login": _format_dt(user.last_login),
        "status": _account_status_label(user),
    }


def _serialize_recent_activity(content: Content) -> dict:
    return {
        "title": content.original_filename,
        "result": _image_decision_label(content),
        "date": _format_date(content.created_at),
    }


def _serialize_user_detail(user: User) -> dict:
    wallet_link = getattr(user, "wallet_link", None)
    recent_contents = list(user.contents.all()[:5])
    return {
        **_serialize_user_list_item(user),
        "recent_ip": "",
        "wallet_address": wallet_link.address if wallet_link else "",
        "wallet_method": wallet_link.wallet_type if wallet_link else "",
        "wallet_linked_at": _format_date(wallet_link.verified_at) if wallet_link else "",
        "vote_permission": _user_vote_permission(user),
        "recent_activities": [_serialize_recent_activity(content) for content in recent_contents],
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
    return {
        "public_id": str(content.public_id),
        "file_name": content.original_filename,
        "uploader_email": content.owner.email or content.owner.username,
        "uploaded_at": _format_date(content.created_at),
        "decision": _image_decision_label(content),
        "preview_url": preview_url,
        "watermark_preview_url": watermark_preview_url,
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
            recent_feed.append(
                f"{_format_dt(content.updated_at)} · {content.owner.email or content.owner.username} · {content.original_filename} · {_image_decision_label(content)}"
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
        payload = _serialize_user_detail(user)
        return Response(AdminUserDetailSerializer(payload).data)

    def patch(self, request, user_id: int):
        user = get_object_or_404(User.objects.select_related("wallet_link"), pk=user_id)
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.update(user, serializer.validated_data)
        payload = _serialize_user_detail(user)
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
