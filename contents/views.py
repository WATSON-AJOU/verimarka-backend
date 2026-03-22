import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.services import AIIntegrationError
from accounts.permissions import IsPhoneVerified

from .serializers import ContentRegisterSerializer, ContentSerializer
from .services import ContentRegistrationService
from .models import Content
from .blockchain_service import ContentBlockchainService
from .watermark_service import ContentWatermarkService

logger = logging.getLogger(__name__)


class ContentRegisterView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ContentRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        upload = serializer.validated_data["file"]
        logger.info(
            "contents.register.request user_id=%s filename=%s size=%s content_type=%s",
            getattr(request.user, "id", None),
            getattr(upload, "name", None),
            getattr(upload, "size", None),
            getattr(upload, "content_type", None),
        )

        try:
            content = ContentRegistrationService.register_image(
                user=request.user,
                upload=upload,
            )
        except AIIntegrationError as exc:
            logger.exception(
                "contents.register.ai_error user_id=%s job_id=%s error_code=%s message=%s",
                getattr(request.user, "id", None),
                exc.job_id,
                exc.error_code,
                exc.error_message,
            )
            return Response(
                exc.to_response().model_dump(),
                status=exc.status_code,
            )

        logger.info(
            "contents.register.success user_id=%s content_id=%s decision=%s next_action=%s",
            getattr(request.user, "id", None),
            content.public_id,
            content.decision,
            content.next_action,
        )

        return Response(
            ContentSerializer(content, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ContentWatermarkView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified]

    def post(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)

        try:
            content = ContentWatermarkService.apply_watermark(content=content)
        except AIIntegrationError as exc:
            logger.exception(
                "contents.watermark.ai_error user_id=%s job_id=%s error_code=%s message=%s",
                getattr(request.user, "id", None),
                exc.job_id,
                exc.error_code,
                exc.error_message,
            )
            return Response(exc.to_response().model_dump(), status=exc.status_code)

        logger.info(
            "contents.watermark.success user_id=%s content_id=%s output_key=%s",
            getattr(request.user, "id", None),
            content.public_id,
            (content.watermark or {}).get("output_key"),
        )
        return Response(ContentSerializer(content, context={"request": request}).data, status=status.HTTP_200_OK)


class ContentMintView(APIView):
    permission_classes = [IsAuthenticated, IsPhoneVerified]

    def post(self, request, public_id):
        content = get_object_or_404(Content, public_id=public_id, owner=request.user)

        try:
            content = ContentBlockchainService.mint(content=content)
        except AIIntegrationError as exc:
            logger.exception(
                "contents.mint.ai_error user_id=%s job_id=%s error_code=%s message=%s",
                getattr(request.user, "id", None),
                exc.job_id,
                exc.error_code,
                exc.error_message,
            )
            return Response(exc.to_response().model_dump(), status=exc.status_code)

        logger.info(
            "contents.mint.success user_id=%s content_id=%s token_id=%s tx_hash=%s",
            getattr(request.user, "id", None),
            content.public_id,
            (content.blockchain or {}).get("token_id"),
            (content.blockchain or {}).get("tx_hash"),
        )
        return Response(ContentSerializer(content, context={"request": request}).data, status=status.HTTP_200_OK)
