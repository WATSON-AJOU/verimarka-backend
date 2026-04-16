import logging
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.models import AIJob
from analysis.tasks import run_register_analysis_job, run_verify_job, run_watermark_job
from accounts.permissions import IsPhoneVerified, IsWalletLinked

from .serializers import ContentRegisterSerializer, ContentSerializer, ContentVerifySerializer
from .serializers import ReviewVoteSignatureSerializer, ReviewVoteStartSerializer
from .services import ContentRegistrationService
from .models import Content, VoteParticipationLog
from .blockchain_service import ContentBlockchainService
from .verification_service import ContentVerificationService
from .watermark_service import ContentWatermarkService
from .storage import S3StorageService

logger = logging.getLogger(__name__)


def _build_async_job_response(job: AIJob, content: Content, request, *, status_code=status.HTTP_202_ACCEPTED):
    return Response(
        {
            "job_id": str(job.public_id),
            "status": job.status,
            "content": ContentSerializer(content, context={"request": request}).data,
        },
        status=status_code,
    )


def _build_watermarked_download_name(filename: str) -> str:
    trimmed = (filename or "").strip()
    if not trimmed:
        return "watermarked_VM"

    dot_index = trimmed.rfind(".")
    if dot_index <= 0 or dot_index == len(trimmed) - 1:
        return f"{trimmed}_VM"

    return f"{trimmed[:dot_index]}_VM{trimmed[dot_index:]}"


def _build_content_preview_url(request, content: Content) -> str | None:
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


def _format_review_vote_summary(content: Content) -> str:
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


def _is_vote_still_open(content: Content) -> bool:
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


class ContentRegisterView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def post(self, request):
        serializer = ContentRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        upload = serializer.validated_data["file"]
        if not S3StorageService.is_enabled():
            return Response(
                {
                    "error_code": "ASYNC_STORAGE_REQUIRED",
                    "error_message": "Celery 비동기 등록 처리를 위해 S3 저장소가 활성화되어야 합니다.",
                    "retryable": False,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        logger.info(
            "contents.register.request user_id=%s filename=%s size=%s content_type=%s",
            getattr(request.user, "id", None),
            getattr(upload, "name", None),
            getattr(upload, "size", None),
            getattr(upload, "content_type", None),
        )

        temp_path, source_sha256 = ContentRegistrationService.write_temp_file_with_hash(upload)
        try:
            matching_contents = list(
                Content.objects.filter(owner=request.user, source_sha256=source_sha256)
                .exclude(status="failed")
                .order_by("-updated_at")
            )
            existing_content = matching_contents[0] if matching_contents else None
            if existing_content is not None:
                existing_job = (
                    AIJob.objects.filter(content=existing_content, owner=request.user, job_type="register")
                    .order_by("-created_at")
                    .first()
                )
                if existing_job is not None and existing_job.status in {"queued", "running"}:
                    logger.info(
                        "contents.register.idempotent_reuse user_id=%s content_id=%s job_id=%s source_sha256=%s",
                        getattr(request.user, "id", None),
                        existing_content.public_id,
                        existing_job.public_id,
                        source_sha256,
                    )
                    return _build_async_job_response(existing_job, existing_content, request)

                blocked_duplicate_source = next(
                    (
                        item
                        for item in matching_contents
                        if (
                            (
                                bool((item.blockchain or {}).get("minted"))
                                and (item.blockchain or {}).get("mint_kind") == "content"
                            )
                            or (
                                bool((item.watermark or {}).get("applied"))
                                and (
                                    (item.watermark or {}).get("output_key")
                                    or (item.watermark or {}).get("output_url")
                                )
                            )
                        )
                    ),
                    None,
                )
                if blocked_duplicate_source is not None:
                    duplicate_content = ContentRegistrationService.create_blocked_duplicate_content(
                        user=request.user,
                        upload=upload,
                        source_sha256=source_sha256,
                        existing_content=blocked_duplicate_source,
                        temp_path=temp_path,
                    )
                    duplicate_job = AIJob.objects.create(
                        owner=request.user,
                        content=duplicate_content,
                        job_type="register",
                        status="success",
                        request_payload={"duplicate_of": str(blocked_duplicate_source.public_id)},
                        response_payload={"content_public_id": str(duplicate_content.public_id)},
                    )
                    return _build_async_job_response(
                        duplicate_job,
                        duplicate_content,
                        request,
                        status_code=status.HTTP_200_OK,
                    )

            content = ContentRegistrationService.create_pending_content(
                user=request.user,
                upload=upload,
                source_sha256=source_sha256,
            )
            source_input = ContentRegistrationService._build_source_input(content, temp_path=temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        job = AIJob.objects.create(
            owner=request.user,
            content=content,
            job_type="register",
            request_payload={"source_input": source_input},
        )
        task = run_register_analysis_job.delay(str(job.public_id))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id", "updated_at"])
        logger.info(
            "contents.register.enqueued user_id=%s content_id=%s job_id=%s celery_task_id=%s",
            getattr(request.user, "id", None),
            content.public_id,
            job.public_id,
            task.id,
        )

        return _build_async_job_response(job, content, request)


class ContentVerifyView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def post(self, request):
        serializer = ContentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        if not S3StorageService.is_enabled():
            return Response(
                {
                    "error_code": "ASYNC_STORAGE_REQUIRED",
                    "error_message": "Celery 비동기 검증 처리를 위해 S3 저장소가 활성화되어야 합니다.",
                    "retryable": False,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            "contents.verify.request user_id=%s filename=%s size=%s content_type=%s",
            getattr(request.user, "id", None),
            getattr(upload, "name", None),
            getattr(upload, "size", None),
            getattr(upload, "content_type", None),
        )

        temp_path = ContentVerificationService._write_temp_file(upload)
        try:
            source_input = ContentVerificationService._build_source_input(temp_path=temp_path, upload=upload)
        finally:
            temp_path.unlink(missing_ok=True)

        job = AIJob.objects.create(
            owner=request.user,
            job_type="verify",
            request_payload={
                "source_input": source_input,
                "upload_name": upload.name,
                "upload_size": upload.size,
                "upload_content_type": getattr(upload, "content_type", "") or "application/octet-stream",
            },
        )
        task = run_verify_job.delay(str(job.public_id))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id", "updated_at"])
        logger.info(
            "contents.verify.enqueued user_id=%s job_id=%s celery_task_id=%s filename=%s",
            getattr(request.user, "id", None),
            job.public_id,
            task.id,
            upload.name,
        )

        return Response(
            {
                "job_id": str(job.public_id),
                "status": job.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ContentWatermarkView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def post(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)
        watermark = content.watermark or {}
        if watermark.get("applied") and (watermark.get("output_key") or watermark.get("output_url")):
            existing_job = (
                AIJob.objects.filter(owner=request.user, content=content, job_type="watermark")
                .order_by("-created_at")
                .first()
            )
            if existing_job is not None:
                logger.info(
                    "contents.watermark.idempotent_completed user_id=%s content_id=%s job_id=%s",
                    getattr(request.user, "id", None),
                    content.public_id,
                    existing_job.public_id,
                )
                return _build_async_job_response(existing_job, content, request, status_code=status.HTTP_200_OK)

        existing_job = (
            AIJob.objects.filter(owner=request.user, content=content, job_type="watermark", status__in=["queued", "running"])
            .order_by("-created_at")
            .first()
        )
        if existing_job is not None:
            logger.info(
                "contents.watermark.idempotent_reuse user_id=%s content_id=%s job_id=%s",
                getattr(request.user, "id", None),
                content.public_id,
                existing_job.public_id,
            )
            return _build_async_job_response(existing_job, content, request)

        job = AIJob.objects.create(
            owner=request.user,
            content=content,
            job_type="watermark",
            request_payload={"content_public_id": str(content.public_id)},
        )
        task = run_watermark_job.delay(str(job.public_id))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id", "updated_at"])
        logger.info(
            "contents.watermark.enqueued user_id=%s content_id=%s job_id=%s celery_task_id=%s",
            getattr(request.user, "id", None),
            content.public_id,
            job.public_id,
            task.id,
        )
        return _build_async_job_response(job, content, request)


class ContentWatermarkDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def get(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)
        watermark = content.watermark or {}
        filename = _build_watermarked_download_name(content.original_filename)
        content_type = content.mime_type or "application/octet-stream"

        output_key = watermark.get("output_key")
        if output_key and S3StorageService.is_enabled():
            client = S3StorageService._get_client()
            obj = client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=output_key)
            response = FileResponse(
                obj["Body"],
                as_attachment=True,
                filename=filename,
                content_type=content_type,
            )
            response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
            return response

        output_path = watermark.get("output_path")
        if output_path and Path(output_path).exists():
            response = FileResponse(
                open(output_path, "rb"),
                as_attachment=True,
                filename=filename,
                content_type=content_type,
            )
            response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
            return response

        output_url = watermark.get("output_url")
        if output_url and not str(output_url).startswith(("http://", "https://")):
            relative_path = str(output_url).replace(settings.MEDIA_URL, "", 1).lstrip("/")
            local_path = Path(settings.MEDIA_ROOT) / relative_path
            if local_path.exists():
                response = FileResponse(
                    open(local_path, "rb"),
                    as_attachment=True,
                    filename=filename,
                    content_type=content_type,
                )
                response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
                return response

        raise Http404("워터마크 파일을 찾을 수 없습니다.")


class ContentMintView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def post(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)

        content = ContentBlockchainService.mint(content=content)

        logger.info(
            "contents.mint.success user_id=%s content_id=%s token_id=%s tx_hash=%s",
            getattr(request.user, "id", None),
            content.public_id,
            (content.blockchain or {}).get("token_id"),
            (content.blockchain or {}).get("tx_hash"),
        )
        return Response(ContentSerializer(content, context={"request": request}).data, status=status.HTTP_200_OK)


class ContentReviewVoteStartView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def post(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)
        serializer = ReviewVoteStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = ContentBlockchainService.start_review_vote(
            content=content,
            notify_by_email=serializer.validated_data["notify_by_email"],
        )

        logger.info(
            "contents.review_vote_start.success user_id=%s content_id=%s token_id=%s vote_id=%s",
            getattr(request.user, "id", None),
            content.public_id,
            (content.blockchain or {}).get("token_id"),
            ((content.blockchain or {}).get("vote") or {}).get("vote_id"),
        )
        return Response(ContentSerializer(content, context={"request": request}).data, status=status.HTTP_200_OK)


class ContentReviewVoteStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)

        content = ContentBlockchainService.sync_review_vote(content=content)

        logger.info(
            "contents.review_vote_status.success user_id=%s content_id=%s status=%s",
            getattr(request.user, "id", None),
            content.public_id,
            ((content.blockchain or {}).get("vote") or {}).get("status"),
        )
        return Response(ContentSerializer(content, context={"request": request}).data, status=status.HTTP_200_OK)


class ContentReviewVoteSigningContextView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def get(self, request, public_id):
        content = get_object_or_404(Content.objects.select_related("owner", "owner__wallet_link"), public_id=public_id)
        wallet_link = getattr(request.user, "wallet_link", None)
        if wallet_link is None or not wallet_link.address:
            return Response({"message": "지갑 연결이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        payload = ContentBlockchainService.get_review_vote_signing_context(
            content=content,
            voter_address=wallet_link.address,
        )

        return Response(payload, status=status.HTTP_200_OK)


class ContentReviewVoteCastView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified, IsWalletLinked]

    def post(self, request, public_id):
        content = get_object_or_404(Content.objects.select_related("owner", "owner__wallet_link"), public_id=public_id)
        wallet_link = getattr(request.user, "wallet_link", None)
        if wallet_link is None or not wallet_link.address:
            return Response({"message": "지갑 연결이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReviewVoteSignatureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content, receipt = ContentBlockchainService.submit_review_vote_signature(
            content=content,
            voter_address=wallet_link.address,
            is_original=serializer.validated_data["is_original"],
            deadline=serializer.validated_data["deadline"],
            signature=serializer.validated_data["signature"],
        )

        VoteParticipationLog.objects.update_or_create(
            content=content,
            user=request.user,
            defaults={
                "wallet_address": wallet_link.address,
                "choice": "yes" if serializer.validated_data["is_original"] else "no",
                "tx_hash": str(receipt.get("tx_hash") or receipt.get("transaction_hash") or ""),
                "token_id": (content.blockchain or {}).get("token_id"),
                "signed_deadline": serializer.validated_data["deadline"],
            },
        )

        logger.info(
            "contents.review_vote_cast.success user_id=%s content_id=%s token_id=%s tx_hash=%s",
            getattr(request.user, "id", None),
            content.public_id,
            (content.blockchain or {}).get("token_id"),
            receipt.get("tx_hash"),
        )
        return Response(
            {
                "tx_hash": receipt.get("tx_hash"),
                "block_number": receipt.get("block_number"),
                "gas_used": receipt.get("gas_used"),
                "content": ContentSerializer(content, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class ContentReviewVoteEventSyncView(APIView):
    permission_classes = []

    def post(self, request):
        secret = (settings.BLOCKCHAIN_EVENT_SYNC_SECRET or "").strip()
        provided = (
            request.headers.get("X-Blockchain-Sync-Secret")
            or request.data.get("secret")
            or ""
        ).strip()

        if not secret or not secrets.compare_digest(secret, provided):
            return Response({"message": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        token_id = request.data.get("token_id")
        try:
            token_id = int(token_id)
        except (TypeError, ValueError):
            return Response({"message": "token_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        content = ContentBlockchainService.sync_review_vote_by_token_id(token_id=token_id)

        if content is None:
            return Response({"message": "content not found."}, status=status.HTTP_404_NOT_FOUND)

        logger.info(
            "contents.review_vote_event_sync.success token_id=%s content_id=%s status=%s",
            token_id,
            content.public_id,
            ((content.blockchain or {}).get("vote") or {}).get("status"),
        )
        return Response(
            {
                "content_public_id": str(content.public_id),
                "token_id": token_id,
                "status": ((content.blockchain or {}).get("vote") or {}).get("status"),
            },
            status=status.HTTP_200_OK,
        )


class OngoingReviewVoteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = []
        queryset = Content.objects.select_related("owner").filter(decision="review").order_by("-updated_at")[:50]

        for content in queryset:
            if not _is_vote_still_open(content):
                continue

            owner_name = (
                getattr(content.owner, "display_name", "")
                or getattr(content.owner, "nickname", "")
                or getattr(content.owner, "username", "")
                or getattr(content.owner, "email", "").split("@")[0]
                or "사용자"
            )

            items.append(
                {
                    "id": str(content.public_id),
                    "title": content.original_filename,
                    "owner": owner_name,
                    "date": timezone.localtime(content.updated_at).strftime("%Y.%m.%d"),
                    "description": _format_review_vote_summary(content),
                    "preview_url": _build_content_preview_url(request, content),
                }
            )

            if len(items) >= 5:
                break

        return Response(items, status=status.HTTP_200_OK)
