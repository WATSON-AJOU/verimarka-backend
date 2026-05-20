import json
import time

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.api.services import AIIntegrationError, AnalysisGuardService
from analysis.models import AIJob
from contents.api.serializers import ContentSerializer

TERMINAL_JOB_STATUSES = {"success", "failure"}
STREAM_HEARTBEAT_SECONDS = 15


def _build_job_payload(
    job: AIJob, request, *, include_content: bool | None = None
) -> dict:
    content_payload = None
    if include_content is None:
        include_content = job.status == "success"
    if include_content and job.content:
        content_payload = ContentSerializer(
            job.content, context={"request": request}
        ).data
    progress = 100 if job.status == "success" else job.progress

    return {
        "job_id": str(job.public_id),
        "job_type": job.job_type,
        "status": job.status,
        "progress": progress,
        "progress_message": job.progress_message,
        "content": content_payload,
        "result": job.response_payload or None,
        "error_code": job.error_code or None,
        "error_message": job.error_message or None,
        "retryable": job.retryable,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


class GuardAnalyzeView(APIView):
    def post(self, request):
        try:
            response = AnalysisGuardService.run_guard_v1(request.data)
        except AIIntegrationError as exc:
            return Response(exc.to_response().model_dump(), status=exc.status_code)
        except Exception:
            return Response(
                {
                    "job_id": request.data.get("job_id"),
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "error_message": "서버 내부 오류가 발생했습니다.",
                    "retryable": True,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(response.model_dump(), status=200)


class AIJobDetailView(APIView):
    def get(self, request, public_id):
        job = get_object_or_404(
            AIJob.objects.select_related("content"),
            public_id=public_id,
            owner=request.user,
        )
        return Response(_build_job_payload(job, request), status=200)


class AIJobStreamView(APIView):
    def get(self, request, public_id):
        get_object_or_404(AIJob, public_id=public_id, owner=request.user)

        def event_stream():
            last_signature = None
            last_heartbeat = time.monotonic()
            deadline = time.monotonic() + 60 * 10
            while time.monotonic() < deadline:
                job = (
                    AIJob.objects.select_related("content")
                    .filter(public_id=public_id, owner=request.user)
                    .first()
                )
                if job is None:
                    yield 'event: error\ndata: {"error":"job_not_found"}\n\n'
                    return

                payload = _build_job_payload(job, request)
                signature = (
                    payload["status"],
                    payload["progress"],
                    payload["progress_message"],
                    payload["completed_at"],
                    json.dumps(payload.get("result"), sort_keys=True, default=str),
                )
                if signature != last_signature:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    last_signature = signature
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= STREAM_HEARTBEAT_SECONDS:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.monotonic()

                if job.status in TERMINAL_JOB_STATUSES:
                    return

                time.sleep(0.5)

            yield 'event: timeout\ndata: {"error":"stream_timeout"}\n\n'

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
