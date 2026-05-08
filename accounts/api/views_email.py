from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api.serializers import EmailSendSerializer, EmailVerifySerializer
from accounts.services.email_service import (
    EmailSendError,
    generate_verification_code,
    send_verification_email,
)
from accounts.services.email_verification_store import (
    EMAIL_VERIFY_DAILY_LIMIT,
    EMAIL_VERIFY_MAX_FAIL_COUNT,
    EMAIL_VERIFY_TTL_SECONDS,
    EmailVerificationStoreError,
    delete_code,
    get_code_hash,
    get_daily_count,
    get_fail_count,
    hash_code,
    increment_daily_count,
    increment_fail_count,
    store_code,
)

User = get_user_model()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


class EmailSendCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EmailSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = normalize_email(serializer.validated_data["email"])
        if not email:
            return Response(
                {"detail": "이메일을 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST
            )

        exists = (
            User.objects.filter(email__iexact=email, email_verified=True)
            .exclude(id=request.user.id)
            .exists()
        )
        if exists:
            return Response(
                {"detail": "이미 다른 계정에서 인증된 이메일입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            today_count = get_daily_count(request.user.id)
        except EmailVerificationStoreError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if today_count >= EMAIL_VERIFY_DAILY_LIMIT:
            return Response(
                {"detail": "하루 최대 3번까지만 인증번호를 요청할 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = generate_verification_code()

        try:
            increment_daily_count(request.user.id)
            store_code(request.user.id, email, code)
            send_verification_email(email, code)
        except (EmailSendError, EmailVerificationStoreError) as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {
                "detail": "인증번호를 이메일로 발송했습니다.",
                "expires_in": EMAIL_VERIFY_TTL_SECONDS,
                "daily_remaining": max(0, (EMAIL_VERIFY_DAILY_LIMIT - 1) - today_count),
            },
            status=status.HTTP_200_OK,
        )


class EmailVerifyCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = normalize_email(serializer.validated_data["email"])
        code = serializer.validated_data["code"]

        try:
            saved_code_hash = get_code_hash(request.user.id, email)
        except EmailVerificationStoreError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if not saved_code_hash:
            return Response(
                {"detail": "인증 요청이 없습니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            fail_count = get_fail_count(request.user.id, email)
        except EmailVerificationStoreError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        if fail_count >= EMAIL_VERIFY_MAX_FAIL_COUNT:
            return Response(
                {
                    "detail": "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if saved_code_hash != hash_code(code):
            try:
                next_fail_count = increment_fail_count(request.user.id, email)
            except EmailVerificationStoreError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            if next_fail_count >= EMAIL_VERIFY_MAX_FAIL_COUNT:
                delete_code(request.user.id, email)
                return Response(
                    {
                        "detail": "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"detail": "인증번호가 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exists = (
            User.objects.filter(email__iexact=email, email_verified=True)
            .exclude(id=request.user.id)
            .exists()
        )
        if exists:
            return Response(
                {"detail": "이미 다른 계정에서 인증된 이메일입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.email = email
        request.user.email_verified = True
        request.user.email_verified_at = timezone.now()
        request.user.save(
            update_fields=["email", "email_verified", "email_verified_at"]
        )
        delete_code(request.user.id, email)

        return Response(
            {
                "detail": "이메일 인증이 완료되었습니다.",
                "email": request.user.email,
                "email_verified": request.user.email_verified,
            },
            status=status.HTTP_200_OK,
        )
