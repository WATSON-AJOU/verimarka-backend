from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.services import AIIntegrationError

from .serializers import ContentRegisterSerializer, ContentSerializer
from .services import ContentRegistrationService


class ContentRegisterView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ContentRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            content = ContentRegistrationService.register_image(
                user=request.user,
                upload=serializer.validated_data["file"],
            )
        except AIIntegrationError as exc:
            return Response(
                exc.to_response().model_dump(),
                status=exc.status_code,
            )

        return Response(
            ContentSerializer(content, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
