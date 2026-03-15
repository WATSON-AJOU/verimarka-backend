import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import SocialAccount
from ..serializers import MeSerializer
from ..services.google_oauth import (
    exchange_code_for_token,
    fetch_userinfo,
    GoogleOAuthError,
)
from ..services.kakao_oauth import (
    exchange_code_for_token as kakao_exchange_code_for_token,
    fetch_userinfo as kakao_fetch_userinfo,
    KakaoOAuthError,
)


User = get_user_model()


class GoogleOAuthLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")
        code_verifier = request.data.get("code_verifier")

        if not code or not redirect_uri:
            return Response(
                {"detail": "code and redirect_uri are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_data = exchange_code_for_token(code, redirect_uri, code_verifier)
            access_token = token_data.get("access_token")
            if not access_token:
                return Response(
                    {"detail": "no access_token from google"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile = fetch_userinfo(access_token)

        except GoogleOAuthError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sub = profile.get("sub")
        email = profile.get("email")

        if not sub:
            return Response(
                {"detail": "google sub missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                social = (
                    SocialAccount.objects.select_related("user")
                    .filter(
                        provider="google",
                        provider_sub=sub,
                    )
                    .first()
                )

                if social:
                    user = social.user
                    created = False
                else:
                    if email and User.objects.filter(email=email).exists():
                        return Response(
                            {"detail": "이미 일반 회원가입 또는 다른 계정에 사용 중인 이메일입니다."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    user = User.objects.create_user(
                        username=f"google_{uuid.uuid4().hex[:20]}",
                        email=email or "",
                    )
                    SocialAccount.objects.create(
                        user=user,
                        provider="google",
                        provider_sub=sub,
                        email=email or "",
                    )
                    created = True

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

        except IntegrityError:
            return Response(
                {"detail": "user creation failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": MeSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_200_OK,
        )


class KakaoOAuthLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")

        if not code or not redirect_uri:
            return Response(
                {"detail": "code and redirect_uri are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_data = kakao_exchange_code_for_token(code, redirect_uri)
            access_token = token_data.get("access_token")
            if not access_token:
                return Response(
                    {"detail": "no access_token from kakao"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile = kakao_fetch_userinfo(access_token)

        except KakaoOAuthError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sub = str(profile.get("id")) if profile.get("id") else None
        kakao_account = profile.get("kakao_account", {}) or {}
        email = kakao_account.get("email")

        if not sub:
            return Response(
                {"detail": "kakao id missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                social = (
                    SocialAccount.objects.select_related("user")
                    .filter(
                        provider="kakao",
                        provider_sub=sub,
                    )
                    .first()
                )

                if social:
                    user = social.user
                    created = False
                else:
                    if email and User.objects.filter(email=email).exists():
                        return Response(
                            {"detail": "이미 일반 회원가입 또는 다른 계정에 사용 중인 이메일입니다."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    user = User.objects.create_user(
                        username=f"kakao_{uuid.uuid4().hex[:20]}",
                        email=email or "",
                    )
                    SocialAccount.objects.create(
                        user=user,
                        provider="kakao",
                        provider_sub=sub,
                        email=email or "",
                    )
                    created = True

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

        except IntegrityError:
            return Response(
                {"detail": "user creation failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": MeSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_200_OK,
        )
