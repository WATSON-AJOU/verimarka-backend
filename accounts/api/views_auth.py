from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.api.serializers import (
    AdminLoginSerializer,
    AdminMeSerializer,
    LoginSerializer,
    MeSerializer,
    SignupSerializer,
)
from accounts.api.token_cookies import (
    clear_refresh_cookie,
    get_refresh_token_from_request,
    set_refresh_cookie,
)


def _get_client_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _record_login_success(request, user) -> None:
    user.last_login = timezone.now()
    user.last_login_ip = _get_client_ip(request)
    user.save(update_fields=["last_login", "last_login_ip"])


def blacklist_refresh_token(raw_refresh: str | None) -> bool:
    if not raw_refresh:
        return False
    try:
        RefreshToken(raw_refresh).blacklist()
        return True
    except (AttributeError, TokenError):
        return False


def build_auth_response(
    *, refresh: RefreshToken, payload: dict, status_code: int
) -> Response:
    response = Response(
        {
            "access": str(refresh.access_token),
            **payload,
        },
        status=status_code,
    )
    return set_refresh_cookie(response, str(refresh))


class CookieTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        if not data.get("refresh"):
            data["refresh"] = get_refresh_token_from_request(request) or ""

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        response_data = dict(serializer.validated_data)
        next_refresh = response_data.pop("refresh", None)
        response = Response(response_data, status=status.HTTP_200_OK)
        if next_refresh:
            set_refresh_cookie(response, str(next_refresh))
        response["Cache-Control"] = "no-store"
        return response


class SignupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return build_auth_response(
            refresh=refresh,
            payload={
                "user": MeSerializer(user).data,
                "created": True,
            },
            status_code=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        _record_login_success(request, user)
        refresh = RefreshToken.for_user(user)

        return build_auth_response(
            refresh=refresh,
            payload={
                "user": MeSerializer(user).data,
            },
            status_code=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        blacklisted = blacklist_refresh_token(get_refresh_token_from_request(request))
        response = Response(
            {
                "message": "로그아웃되었습니다.",
                "refresh_blacklisted": blacklisted,
            },
            status=status.HTTP_200_OK,
        )
        return clear_refresh_cookie(response)


class AdminLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        _record_login_success(request, user)
        refresh = RefreshToken.for_user(user)

        return build_auth_response(
            refresh=refresh,
            payload={
                "user": AdminMeSerializer(user).data,
            },
            status_code=status.HTTP_200_OK,
        )


class AdminMeView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(AdminMeSerializer(request.user).data, status=status.HTTP_200_OK)
