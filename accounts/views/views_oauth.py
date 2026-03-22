import uuid
from django.utils import timezone

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


def build_social_identity(provider: str, email: str | None) -> dict[str, str]:
    base_name = (email or provider).split("@")[0].strip() or provider
    suffix = uuid.uuid4().hex[:8]
    nickname = f"{base_name[:20]}_{suffix}"

    return {
        "username": f"{provider}_{uuid.uuid4().hex[:20]}",
        "nickname": nickname[:30],
        "display_name": base_name[:50],
    }


def get_oauth_agreement_defaults() -> dict[str, timezone.datetime]:
    agreed_at = timezone.now()
    return {
        "terms_agreed_at": agreed_at,
        "privacy_agreed_at": agreed_at,
    }


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
                    if user.is_deleted or not user.is_active:
                        return Response(
                            {"detail": "탈퇴한 계정입니다. 고객센터로 문의해주세요."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    created = False
                else:
                    if email and User.objects.filter(email=email).exists():
                        return Response(
                            {"detail": "이미 일반 회원가입 또는 다른 계정에 사용 중인 이메일입니다."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    identity = build_social_identity("google", email)
                    user = User.objects.create_user(
                        username=identity["username"],
                        nickname=identity["nickname"],
                        display_name=identity["display_name"],
                        auth_provider="google",
                        email=email or "",
                        **get_oauth_agreement_defaults(),
                    )
                    SocialAccount.objects.create(
                        user=user,
                        provider="google",
                        provider_sub=sub,
                        email=email or "",
                        last_login_at=timezone.now(),
                    )
                    created = True

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

                social = SocialAccount.objects.get(provider="google", provider_sub=sub)
                social.last_login_at = timezone.now()
                social.save(update_fields=["last_login_at"])

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
                    if user.is_deleted or not user.is_active:
                        return Response(
                            {"detail": "탈퇴한 계정입니다. 고객센터로 문의해주세요."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    created = False
                else:
                    if email and User.objects.filter(email=email).exists():
                        return Response(
                            {"detail": "이미 일반 회원가입 또는 다른 계정에 사용 중인 이메일입니다."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    identity = build_social_identity("kakao", email)
                    user = User.objects.create_user(
                        username=identity["username"],
                        nickname=identity["nickname"],
                        display_name=identity["display_name"],
                        auth_provider="kakao",
                        email=email or "",
                        **get_oauth_agreement_defaults(),
                    )
                    SocialAccount.objects.create(
                        user=user,
                        provider="kakao",
                        provider_sub=sub,
                        email=email or "",
                        last_login_at=timezone.now(),
                    )
                    created = True

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

                social = SocialAccount.objects.get(provider="kakao", provider_sub=sub)
                social.last_login_at = timezone.now()
                social.save(update_fields=["last_login_at"])

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
