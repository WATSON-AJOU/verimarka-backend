from django.contrib.auth import get_user_model
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.models import AIJob
from analysis.tasks import run_register_analysis_job, run_verify_job, run_watermark_job
from contents.models import Content
from operations.api.serializers import (
    AdminActionLogSerializer,
    ModerationCaseCreateSerializer,
    ModerationCaseSerializer,
    NotificationCreateSerializer,
    NotificationSerializer,
    OperationPayloadSerializer,
    PolicyVersionCreateSerializer,
    PolicyVersionSerializer,
    ReportCaseCreateSerializer,
    ReportCaseSerializer,
    ReportCaseUpdateSerializer,
    RetentionRequestCreateSerializer,
    RetentionRequestSerializer,
    RetentionRequestUpdateSerializer,
)
from operations.api.utils import log_admin_action
from operations.models import (
    AdminActionLog,
    ModerationCase,
    Notification,
    PolicyVersion,
    ReportCase,
    RetentionRequest,
)

User = get_user_model()

DEFAULT_PAGE_SIZE = 15
MAX_PAGE_SIZE = 100


def _date_param(value):
    if not value:
        return None
    try:
        return timezone.datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _parse_positive_int(value, default: int, *, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(1, parsed)
    return min(parsed, maximum) if maximum is not None else parsed


def _paginate_queryset(queryset, request):
    page_size = _parse_positive_int(
        request.query_params.get("page_size"),
        DEFAULT_PAGE_SIZE,
        maximum=MAX_PAGE_SIZE,
    )
    requested_page = _parse_positive_int(request.query_params.get("page"), 1)
    paginator = Paginator(queryset, page_size)
    total_pages = max(1, paginator.num_pages)
    page_number = min(requested_page, total_pages)
    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page_number = total_pages
        page = paginator.page(page_number)
    return page, {
        "page": page_number,
        "page_size": page_size,
        "total_count": paginator.count,
        "total_pages": total_pages,
    }


def _paginated_response(serializer_class, queryset, request):
    page, pagination = _paginate_queryset(queryset, request)
    return {
        "results": serializer_class(page.object_list, many=True).data,
        **pagination,
    }


def _content_state(content: Content) -> dict:
    return {
        "status": content.status,
        "decision": content.decision,
        "reason": content.reason,
        "next_action": content.next_action,
    }


def _apply_moderation_action(content: Content, action: str, reason: str) -> None:
    if action == "approve":
        content.status = "allow"
        content.decision = "allow"
        content.next_action = "watermark"
    elif action in {"reject", "hide"}:
        content.status = "block"
        content.decision = "block"
        content.next_action = "none"
    elif action == "needs_review":
        content.status = "review"
        content.decision = "review"
        content.next_action = "start_vote"
    elif action == "restore":
        content.status = "pending"
        content.decision = ""
        content.next_action = "reanalyze"
    elif action == "reanalyze":
        content.status = "pending"
        content.decision = ""
        content.next_action = "reanalyze"
    content.reason = reason
    content.save(
        update_fields=[
            "status",
            "decision",
            "reason",
            "next_action",
            "updated_at",
        ]
    )


def _enqueue_retry_job(job: AIJob) -> AIJob:
    retry_job = AIJob.objects.create(
        owner=job.owner,
        content=job.content,
        job_type=job.job_type,
        status="queued",
        progress=5,
        progress_message="관리자 재처리 요청으로 대기열에 추가되었습니다.",
        request_payload=job.request_payload,
        retryable=False,
    )
    task_map = {
        "register": run_register_analysis_job,
        "verify": run_verify_job,
        "watermark": run_watermark_job,
    }
    task = task_map[retry_job.job_type].delay(str(retry_job.public_id))
    retry_job.celery_task_id = task.id
    retry_job.save(update_fields=["celery_task_id", "updated_at"])
    return retry_job


class AdminOperationsSummaryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        payload = {
            "open_reports": ReportCase.objects.exclude(
                status__in=["resolved", "rejected"]
            ).count(),
            "pending_retention_requests": RetentionRequest.objects.filter(
                status__in=["requested", "approved"]
            ).count(),
            "failed_jobs": AIJob.objects.filter(status="failure").count(),
            "running_jobs": AIJob.objects.filter(
                status__in=["queued", "running"]
            ).count(),
            "moderation_cases_today": ModerationCase.objects.filter(
                created_at__date=timezone.localdate()
            ).count(),
            "notifications_queued": Notification.objects.filter(
                status="queued"
            ).count(),
            "latest_actions": AdminActionLogSerializer(
                AdminActionLog.objects.select_related("actor")[:8], many=True
            ).data,
            "report_status_counts": list(
                ReportCase.objects.values("status")
                .annotate(count=Count("id"))
                .order_by("status")
            ),
        }
        return Response(OperationPayloadSerializer(payload).data)


class AdminActionLogListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = AdminActionLog.objects.select_related("actor").order_by(
            "-created_at"
        )
        action = (request.query_params.get("action") or "").strip()
        target_type = (request.query_params.get("target_type") or "").strip()
        query = (request.query_params.get("q") or "").strip()
        created_from = _date_param(request.query_params.get("created_from"))
        created_to = _date_param(request.query_params.get("created_to"))
        if action:
            queryset = queryset.filter(action=action)
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        if query:
            queryset = queryset.filter(
                Q(actor__email__icontains=query)
                | Q(actor__username__icontains=query)
                | Q(target_id__icontains=query)
                | Q(reason__icontains=query)
                | Q(request_id__icontains=query)
            )
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)
        return Response(
            OperationPayloadSerializer(
                _paginated_response(AdminActionLogSerializer, queryset, request)
            ).data
        )


class AdminModerationCaseListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = ModerationCase.objects.select_related("actor", "content").order_by(
            "-created_at"
        )
        return Response(
            OperationPayloadSerializer(
                _paginated_response(ModerationCaseSerializer, queryset, request)
            ).data
        )

    def post(self, request):
        serializer = ModerationCaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = get_object_or_404(
            Content, public_id=serializer.validated_data["content_public_id"]
        )
        before = _content_state(content)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data["reason"]
        _apply_moderation_action(content, action, reason)
        after = _content_state(content)
        moderation_case = ModerationCase.objects.create(
            content=content,
            actor=request.user,
            action=action,
            reason=reason,
            previous_status=before["status"],
            previous_decision=before["decision"],
            next_status=after["status"],
            next_decision=after["decision"],
            resolved_at=timezone.now(),
        )
        log_admin_action(
            request=request,
            action="content_moderation",
            target_type="content",
            target_id=content.public_id,
            reason=reason,
            before=before,
            after=after,
        )
        if action == "reanalyze":
            latest_register_job = (
                content.ai_jobs.filter(job_type="register")
                .order_by("-created_at")
                .first()
            )
            if latest_register_job is not None:
                _enqueue_retry_job(latest_register_job)
        return Response(
            ModerationCaseSerializer(moderation_case).data,
            status=status.HTTP_201_CREATED,
        )


class PublicReportCaseCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReportCaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = get_object_or_404(
            Content, public_id=serializer.validated_data["content_public_id"]
        )
        report = ReportCase.objects.create(
            reporter=request.user,
            content=content,
            report_type=serializer.validated_data["report_type"],
            title=serializer.validated_data["title"],
            description=serializer.validated_data["description"],
            evidence=serializer.validated_data.get("evidence") or {},
        )
        return Response(
            ReportCaseSerializer(report).data, status=status.HTTP_201_CREATED
        )


class AdminReportCaseListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = ReportCase.objects.select_related(
            "reporter", "assignee", "content"
        ).order_by("-created_at")
        status_filter = (request.query_params.get("status") or "").strip()
        report_type = (request.query_params.get("report_type") or "").strip()
        query = (request.query_params.get("q") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(resolution__icontains=query)
                | Q(content__original_filename__icontains=query)
                | Q(reporter__email__icontains=query)
                | Q(assignee__email__icontains=query)
            )
        return Response(
            OperationPayloadSerializer(
                _paginated_response(ReportCaseSerializer, queryset, request)
            ).data
        )


class AdminReportCaseDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, report_id: int):
        report = get_object_or_404(ReportCase, pk=report_id)
        serializer = ReportCaseUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {
            "status": report.status,
            "assignee_id": report.assignee_id,
            "resolution": report.resolution,
        }
        if "status" in serializer.validated_data:
            report.status = serializer.validated_data["status"]
            if report.status in {"resolved", "rejected"}:
                report.resolved_at = timezone.now()
            else:
                report.resolved_at = None
        if "resolution" in serializer.validated_data:
            report.resolution = serializer.validated_data["resolution"]
        if serializer.validated_data.get("assign_to_me"):
            report.assignee = request.user
        report.save(
            update_fields=[
                "status",
                "resolution",
                "assignee",
                "resolved_at",
                "updated_at",
            ]
        )
        after = {
            "status": report.status,
            "assignee_id": report.assignee_id,
            "resolution": report.resolution,
        }
        log_admin_action(
            request=request,
            action="report_update",
            target_type="report",
            target_id=report.pk,
            reason=report.resolution,
            before=before,
            after=after,
        )
        return Response(ReportCaseSerializer(report).data)


class AdminPolicyVersionListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = PolicyVersion.objects.order_by("policy_type", "-created_at")
        return Response(PolicyVersionSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = PolicyVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publish = serializer.validated_data.pop("publish", False)
        policy = PolicyVersion.objects.create(**serializer.validated_data)
        if publish:
            PolicyVersion.objects.filter(policy_type=policy.policy_type).exclude(
                pk=policy.pk
            ).update(is_active=False)
            policy.is_active = True
            policy.published_at = timezone.now()
            policy.save(update_fields=["is_active", "published_at", "updated_at"])
            log_admin_action(
                request=request,
                action="policy_publish",
                target_type="policy",
                target_id=policy.pk,
                reason=f"{policy.policy_type}:{policy.version}",
                after={"policy_type": policy.policy_type, "version": policy.version},
            )
        return Response(
            PolicyVersionSerializer(policy).data, status=status.HTTP_201_CREATED
        )


class AdminRetentionRequestListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = RetentionRequest.objects.select_related("requester").order_by(
            "-created_at"
        )
        return Response(
            OperationPayloadSerializer(
                _paginated_response(RetentionRequestSerializer, queryset, request)
            ).data
        )

    def post(self, request):
        serializer = RetentionRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        retention = RetentionRequest.objects.create(
            requester=request.user,
            **serializer.validated_data,
        )
        log_admin_action(
            request=request,
            action="retention_update",
            target_type="retention",
            target_id=retention.pk,
            reason=retention.reason,
            after={"status": retention.status},
        )
        return Response(
            RetentionRequestSerializer(retention).data,
            status=status.HTTP_201_CREATED,
        )


class AdminRetentionRequestDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, retention_id: int):
        retention = get_object_or_404(RetentionRequest, pk=retention_id)
        serializer = RetentionRequestUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {"status": retention.status, "decision_note": retention.decision_note}
        if "status" in serializer.validated_data:
            retention.status = serializer.validated_data["status"]
            if retention.status == "completed":
                retention.completed_at = timezone.now()
        if "decision_note" in serializer.validated_data:
            retention.decision_note = serializer.validated_data["decision_note"]
        retention.save(
            update_fields=[
                "status",
                "decision_note",
                "completed_at",
                "updated_at",
            ]
        )
        after = {"status": retention.status, "decision_note": retention.decision_note}
        log_admin_action(
            request=request,
            action="retention_update",
            target_type="retention",
            target_id=retention.pk,
            reason=retention.decision_note,
            before=before,
            after=after,
        )
        return Response(RetentionRequestSerializer(retention).data)


class AdminNotificationListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = Notification.objects.select_related("user").order_by("-created_at")
        return Response(
            OperationPayloadSerializer(
                _paginated_response(NotificationSerializer, queryset, request)
            ).data
        )

    def post(self, request):
        serializer = NotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=serializer.validated_data.pop("user_id"))
        notification = Notification.objects.create(
            user=user, **serializer.validated_data
        )
        log_admin_action(
            request=request,
            action="notification_create",
            target_type="notification",
            target_id=notification.pk,
            reason=notification.title,
            after={"user_id": user.pk, "channel": notification.channel},
        )
        return Response(
            NotificationSerializer(notification).data,
            status=status.HTTP_201_CREATED,
        )


class AdminJobListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = AIJob.objects.select_related("owner", "content").order_by(
            "-created_at"
        )
        status_filter = (request.query_params.get("status") or "").strip()
        job_type = (request.query_params.get("job_type") or "").strip()
        query = (request.query_params.get("q") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if job_type:
            queryset = queryset.filter(job_type=job_type)
        if query:
            queryset = queryset.filter(
                Q(public_id__icontains=query)
                | Q(owner__email__icontains=query)
                | Q(owner__username__icontains=query)
                | Q(content__public_id__icontains=query)
                | Q(content__original_filename__icontains=query)
                | Q(error_code__icontains=query)
                | Q(error_message__icontains=query)
            )
        page, pagination = _paginate_queryset(queryset, request)
        payload = []
        for job in page.object_list:
            payload.append(
                {
                    "job_id": str(job.public_id),
                    "owner_email": job.owner.email or job.owner.username,
                    "content_public_id": str(job.content.public_id)
                    if job.content_id
                    else "",
                    "job_type": job.job_type,
                    "status": job.status,
                    "progress": job.progress,
                    "progress_message": job.progress_message,
                    "error_code": job.error_code,
                    "error_message": job.error_message,
                    "retryable": job.retryable,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                }
            )
        return Response(
            OperationPayloadSerializer({"results": payload, **pagination}).data
        )


class AdminJobDetailView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, job_id, action: str):
        job = get_object_or_404(AIJob, public_id=job_id)
        before = {"status": job.status, "progress": job.progress}
        if action == "retry":
            if job.job_type not in {"register", "verify", "watermark"}:
                return Response(
                    {"detail": "재처리할 수 없는 job 유형입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            retry_job = _enqueue_retry_job(job)
            log_admin_action(
                request=request,
                action="job_retry",
                target_type="ai_job",
                target_id=job.public_id,
                reason="관리자 재처리",
                before=before,
                after={"retry_job_id": str(retry_job.public_id)},
            )
            return Response(
                {
                    "job_id": str(retry_job.public_id),
                    "status": retry_job.status,
                    "progress": retry_job.progress,
                },
                status=status.HTTP_201_CREATED,
            )
        if action == "cancel":
            if job.status not in {"queued", "running"}:
                return Response(
                    {"detail": "대기 또는 실행 중인 job만 취소할 수 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            job.status = "failure"
            job.error_code = "ADMIN_CANCELLED"
            job.error_message = "관리자가 작업을 취소했습니다."
            job.completed_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "completed_at",
                    "updated_at",
                ]
            )
            log_admin_action(
                request=request,
                action="job_cancel",
                target_type="ai_job",
                target_id=job.public_id,
                reason="관리자 취소",
                before=before,
                after={"status": job.status, "error_code": job.error_code},
            )
            return Response({"job_id": str(job.public_id), "status": job.status})
        return Response(
            {"detail": "지원하지 않는 job 액션입니다."},
            status=status.HTTP_404_NOT_FOUND,
        )
