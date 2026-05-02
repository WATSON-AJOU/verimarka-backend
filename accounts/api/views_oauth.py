import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.api.serializers import MeSerializer
from accounts.models import SocialAccount
from accounts.services.apple_oauth import (
    AppleOAuthError,
    exchange_code_for_token as apple_exchange_code_for_token,
    verify_identity_token as apple_verify_identity_token,
)
from accounts.services.google_oauth import (
    GoogleOAuthError,
    exchange_code_for_token,
    fetch_userinfo,
)
from accounts.services.kakao_oauth import (
    KakaoOAuthError,
    exchange_code_for_token as kakao_exchange_code_for_token,
    fetch_userinfo as kakao_fetch_userinfo,
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


def _get_client_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _record_social_login_success(request, user) -> None:
    user.last_login = timezone.now()
    user.last_login_ip = _get_client_ip(request)
    user.save(update_fields=["last_login", "last_login_ip"])


def _get_existing_active_user_by_email(email: str | None):
    if not email:
        return None
    return User.objects.filter(email=email).first()


def _validate_loginable_user(user):
    if user.is_deleted:
        return Response(
            {"detail": "탈퇴한 계정입니다. 고객센터로 문의해주세요."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not user.is_active:
        return Response(
            {"detail": "사용 정지된 계정입니다."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _get_or_create_social_user(*, provider: str, sub: str, email: str | None):
    social = (
        SocialAccount.objects.select_related("user")
        .filter(provider=provider, provider_sub=sub)
        .first()
    )
    if social:
        user = social.user
        return user, social, False, _validate_loginable_user(user)

    user = _get_existing_active_user_by_email(email)
    if user:
        error_response = _validate_loginable_user(user)
        if error_response is not None:
            return None, None, False, error_response

        existing_provider_link = user.social_accounts.filter(provider=provider).first()
        if existing_provider_link:
            return (
                None,
                None,
                False,
                Response(
                    {"detail": "이미 다른 소셜 계정에 연결된 이메일입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )

        social = SocialAccount.objects.create(
            user=user,
            provider=provider,
            provider_sub=sub,
            email=email or "",
            last_login_at=timezone.now(),
        )
        return user, social, False, None

    identity = build_social_identity(provider, email)
    user = User.objects.create_user(
        username=identity["username"],
        nickname=identity["nickname"],
        display_name=identity["display_name"],
        auth_provider=provider,
        email=email or "",
        **get_oauth_agreement_defaults(),
    )
    social = SocialAccount.objects.create(
        user=user,
        provider=provider,
        provider_sub=sub,
        email=email or "",
        last_login_at=timezone.now(),
    )
    return user, social, True, None


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

        except GoogleOAuthError as exc:
            return Response(
                {"detail": str(exc)},
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
                user, social, created, error_response = _get_or_create_social_user(
                    provider="google",
                    sub=sub,
                    email=email,
                )
                if error_response is not None:
                    return error_response

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

                social.last_login_at = timezone.now()
                social.save(update_fields=["last_login_at"])
                _record_social_login_success(request, user)

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

        except KakaoOAuthError as exc:
            return Response(
                {"detail": str(exc)},
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
                user, social, created, error_response = _get_or_create_social_user(
                    provider="kakao",
                    sub=sub,
                    email=email,
                )
                if error_response is not None:
                    return error_response

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

                social.last_login_at = timezone.now()
                social.save(update_fields=["last_login_at"])
                _record_social_login_success(request, user)

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


class AppleOAuthLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")
        identity_token = request.data.get("id_token")

        if not code or not redirect_uri:
            return Response(
                {"detail": "code and redirect_uri are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_data = apple_exchange_code_for_token(code, redirect_uri)
            raw_identity_token = identity_token or token_data.get("id_token")
            if not raw_identity_token:
                return Response(
                    {"detail": "no id_token from apple"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile = apple_verify_identity_token(raw_identity_token)

        except AppleOAuthError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sub = profile.get("sub")
        email = profile.get("email")

        if not sub:
            return Response(
                {"detail": "apple sub missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                user, social, created, error_response = _get_or_create_social_user(
                    provider="apple",
                    sub=sub,
                    email=email,
                )
                if error_response is not None:
                    return error_response

                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=["email"])

                social.last_login_at = timezone.now()
                social.save(update_fields=["last_login_at"])
                _record_social_login_success(request, user)

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
