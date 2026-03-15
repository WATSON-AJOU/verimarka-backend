import hashlib
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from ..models import SmsVerification
from ..serializers import PhoneSendSerializer, PhoneVerifySerializer

from ..services.sms_service import (
    generate_verification_code,
    send_verification_sms,
    SmsSendError,
)

User = get_user_model()


def normalize_phone(phone: str) -> str:
    return re.sub(r"[^0-9]", "", phone or "")


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class PhoneSendCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PhoneSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = normalize_phone(serializer.validated_data["phone"])

        if len(phone) not in (10, 11):
            return Response(
                {"detail": "invalid phone number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exists = (
            User.objects.filter(
                phone=phone,
                phone_verified=True,
            )
            .exclude(id=request.user.id)
            .exists()
        )

        if exists:
            return Response(
                {"detail": "이미 다른 계정에서 인증된 전화번호입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today_start = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_count = SmsVerification.objects.filter(
            phone=phone,
            created_at__gte=today_start,
        ).count()

        if today_count >= 3:
            return Response(
                {"detail": "하루 최대 3번까지만 인증번호를 요청할 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = generate_verification_code()

        verification = SmsVerification.objects.create(
            phone=phone,
            code_hash=hash_code(code),
            expires_at=timezone.now() + timedelta(minutes=3),
            send_count=1,
        )

        try:
            send_verification_sms(phone, code)
        except SmsSendError as e:
            verification.delete()
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "detail": "인증번호를 발송했습니다.",
                "expires_in": 180,
                "daily_remaining": max(0, 2 - today_count),
            },
            status=status.HTTP_200_OK,
        )


class PhoneVerifyCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PhoneVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = normalize_phone(serializer.validated_data["phone"])
        code = serializer.validated_data["code"]

        verification = (
            SmsVerification.objects.filter(phone=phone).order_by("-created_at").first()
        )

        if not verification:
            return Response(
                {"detail": "인증 요청이 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verification.verified_at is not None:
            return Response(
                {"detail": "이미 인증이 완료된 요청입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verification.is_expired():
            return Response(
                {"detail": "인증번호가 만료되었습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verification.code_hash != hash_code(code):
            verification.fail_count += 1
            verification.save(update_fields=["fail_count"])
            return Response(
                {"detail": "인증번호가 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exists = (
            User.objects.filter(
                phone=phone,
                phone_verified=True,
            )
            .exclude(id=request.user.id)
            .exists()
        )

        if exists:
            return Response(
                {"detail": "이미 다른 계정에서 인증된 전화번호입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.phone = phone
        request.user.phone_verified = True
        request.user.save(update_fields=["phone", "phone_verified"])

        verification.verified_at = timezone.now()
        verification.save(update_fields=["verified_at"])

        return Response(
            {
                "detail": "전화번호 인증이 완료되었습니다.",
                "phone": request.user.phone,
                "phone_verified": request.user.phone_verified,
            },
            status=status.HTTP_200_OK,
        )
