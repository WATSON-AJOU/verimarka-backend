from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.models import AIJob
from analysis.api.services import AnalysisGuardService
from contents.api.serializers import ContentSerializer


class GuardAnalyzeView(APIView):
    def post(self, request):
        response = AnalysisGuardService.run_guard_v1(request.data)
        return Response(response.model_dump(), status=200)


class AIJobDetailView(APIView):
    def get(self, request, public_id):
        job = get_object_or_404(AIJob.objects.select_related("content"), public_id=public_id, owner=request.user)
        content_payload = None
        if job.content:
            content_payload = ContentSerializer(job.content, context={"request": request}).data

        return Response(
            {
                "job_id": str(job.public_id),
                "job_type": job.job_type,
                "status": job.status,
                "content": content_payload,
                "result": job.response_payload or None,
                "error_code": job.error_code or None,
                "error_message": job.error_message or None,
                "retryable": job.retryable,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            },
            status=200,
        )
