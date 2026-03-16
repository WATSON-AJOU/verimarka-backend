from rest_framework.response import Response
from rest_framework.views import APIView

from .services import AIIntegrationError, AnalysisGuardService


class GuardAnalyzeView(APIView):
    def post(self, request):
        try:
            response = AnalysisGuardService.run_guard_v1(request.data)
        except AIIntegrationError as exc:
            return Response(
                exc.to_response().model_dump(),
                status=exc.status_code,
            )

        return Response(response.model_dump(), status=200)
