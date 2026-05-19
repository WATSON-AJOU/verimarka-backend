import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from analysis.api.services import AIIntegrationError
from analysis.models import AIJob
from contents.api.services import ContentRegistrationService
from contents.verification_service import ContentVerificationService
from contents.watermark_service import ContentWatermarkService
from logs.models import VerificationHistoryLog

logger = logging.getLogger(__name__)


def _update_job_progress(job: AIJob, progress: int, message: str = "") -> None:
    job.progress = max(0, min(progress, 100))
    job.progress_message = message
    job.save(update_fields=["progress", "progress_message", "updated_at"])


def _mark_job_running(job: AIJob, task_id: str) -> None:
    logger.info(
        "analysis.job.running job_id=%s job_type=%s task_id=%s",
        job.public_id,
        job.job_type,
        task_id,
    )
    job.status = "running"
    job.celery_task_id = task_id
    job.started_at = timezone.now()
    job.error_code = ""
    job.error_message = ""
    job.retryable = False
    job.progress = max(job.progress, 10)
    job.progress_message = "작업을 시작했습니다."
    job.save(
        update_fields=[
            "status",
            "celery_task_id",
            "started_at",
            "error_code",
            "error_message",
            "retryable",
            "progress",
            "progress_message",
            "updated_at",
        ]
    )


def _mark_job_success(job: AIJob, payload: dict) -> None:
    logger.info(
        "analysis.job.success job_id=%s job_type=%s payload=%s",
        job.public_id,
        job.job_type,
        payload,
    )
    job.status = "success"
    job.response_payload = payload
    job.completed_at = timezone.now()
    job.progress = 100
    job.progress_message = "작업이 완료되었습니다."
    job.save(
        update_fields=[
            "status",
            "response_payload",
            "completed_at",
            "progress",
            "progress_message",
            "updated_at",
        ]
    )


def _mark_job_failure(
    job: AIJob, *, error_code: str, error_message: str, retryable: bool
) -> None:
    logger.error(
        "analysis.job.failure job_id=%s job_type=%s error_code=%s retryable=%s message=%s",
        job.public_id,
        job.job_type,
        error_code,
        retryable,
        error_message,
    )
    job.status = "failure"
    job.error_code = error_code
    job.error_message = error_message
    job.retryable = retryable
    job.completed_at = timezone.now()
    job.progress_message = error_message or "작업이 실패했습니다."
    job.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "retryable",
            "completed_at",
            "progress_message",
            "updated_at",
        ]
    )


@shared_task(bind=True, queue="ai")
def run_register_analysis_job(self, job_public_id: str) -> dict:
    job = AIJob.objects.select_related("content", "owner").get(
        public_id=job_public_id, job_type="register"
    )
    _mark_job_running(job, self.request.id)

    try:
        if job.request_payload.get("content_type") == "document":
            _update_job_progress(job, 20, "문서 등록 입력을 검증하고 있습니다.")
            _update_job_progress(job, 35, "문서 등록 워크플로우를 요청하고 있습니다.")
            content = ContentRegistrationService.register_document(
                content=job.content,
                user=job.owner,
                source_input=job.request_payload["source_input"],
            )
            _update_job_progress(
                job, 78, "문서 워터마크 및 OCR 결과를 반영하고 있습니다."
            )
        else:
            _update_job_progress(job, 20, "이미지 분석 입력을 검증하고 있습니다.")
            _update_job_progress(job, 35, "AI 유사도 분석을 요청하고 있습니다.")
            content = ContentRegistrationService.run_guard_for_content(
                content=job.content,
                user_id=job.owner_id,
                source_input=job.request_payload["source_input"],
            )
        _update_job_progress(job, 90, "분석 결과를 저장하고 있습니다.")
        payload = {"content_public_id": str(content.public_id)}
        if (
            job.request_payload.get("content_type") == "document"
            and content.decision == "failed"
        ):
            job.response_payload = payload
            job.save(update_fields=["response_payload", "updated_at"])
            _mark_job_failure(
                job,
                error_code="DOCUMENT_REGISTER_FAILED",
                error_message=content.reason or "문서 등록 처리에 실패했습니다.",
                retryable=False,
            )
            return payload
        _mark_job_success(job, payload)
        return payload
    except AIIntegrationError as exc:
        logger.exception(
            "analysis.job.register_failed job_id=%s content_id=%s",
            job.public_id,
            getattr(job.content, "public_id", None),
        )
        if job.content:
            job.content.status = "failed"
            job.content.reason = exc.error_message
            job.content.save(update_fields=["status", "reason", "updated_at"])
        _mark_job_failure(
            job,
            error_code=exc.error_code,
            error_message=exc.error_message,
            retryable=exc.retryable,
        )
        raise


@shared_task(bind=True, queue="ai")
def run_verify_job(self, job_public_id: str) -> dict:
    job = AIJob.objects.select_related("owner").get(
        public_id=job_public_id, job_type="verify"
    )
    _mark_job_running(job, self.request.id)

    try:
        user = get_user_model().objects.get(pk=job.owner_id)
        _update_job_progress(job, 18, "검증 입력 파일을 준비하고 있습니다.")
        payload = ContentVerificationService.verify_from_source_input(
            user=user,
            upload_name=job.request_payload["upload_name"],
            upload_size=job.request_payload["upload_size"],
            upload_content_type=job.request_payload["upload_content_type"],
            content_type=job.request_payload.get("content_type", "image"),
            source_input=job.request_payload["source_input"],
            uploaded_preview_url=job.request_payload.get("uploaded_preview_url"),
            progress_callback=lambda progress, message: _update_job_progress(
                job, progress, message
            ),
        )
        _update_job_progress(job, 85, "검증 결과를 기록하고 있습니다.")
        uploaded = payload.get("uploaded") or {}
        source_input = job.request_payload.get("source_input") or {}
        VerificationHistoryLog.objects.create(
            user=user,
            outcome=payload.get("outcome", "candidate"),
            uploaded_file_name=uploaded.get("file_name")
            or job.request_payload["upload_name"],
            uploaded_file_size=uploaded.get("file_size")
            or job.request_payload["upload_size"],
            uploaded_storage_key=source_input.get("s3_key") or "",
            uploaded_preview_url=uploaded.get("preview_url"),
            detect=payload.get("detect") or {},
            blockchain=payload.get("blockchain") or {},
            candidate=payload.get("candidate") or {},
            summary=(
                f"워터마크 검증 성공 · Token #{((payload.get('blockchain') or {}).get('token_id') or '-')}"
                if payload.get("outcome") == "verified"
                else (
                    (payload.get("candidate") or {}).get("summary")
                    or "검증 실패 · 추가 확인 필요"
                )
            ),
        )
        _mark_job_success(job, payload)
        return payload
    except AIIntegrationError as exc:
        logger.exception("analysis.job.verify_failed job_id=%s", job.public_id)
        _mark_job_failure(
            job,
            error_code=exc.error_code,
            error_message=exc.error_message,
            retryable=exc.retryable,
        )
        raise


@shared_task(bind=True, queue="ai")
def run_watermark_job(self, job_public_id: str) -> dict:
    job = AIJob.objects.select_related("content").get(
        public_id=job_public_id, job_type="watermark"
    )
    _mark_job_running(job, self.request.id)

    try:
        _update_job_progress(job, 25, "워터마크 삽입을 요청하고 있습니다.")
        content = ContentWatermarkService.apply_watermark(content=job.content)
        _update_job_progress(job, 90, "워터마크 결과를 저장하고 있습니다.")
        payload = {"content_public_id": str(content.public_id)}
        _mark_job_success(job, payload)
        return payload
    except AIIntegrationError as exc:
        logger.exception(
            "analysis.job.watermark_failed job_id=%s content_id=%s",
            job.public_id,
            getattr(job.content, "public_id", None),
        )
        _mark_job_failure(
            job,
            error_code=exc.error_code,
            error_message=exc.error_message,
            retryable=exc.retryable,
        )
        raise
