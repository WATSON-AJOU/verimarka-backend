from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import MeSerializer
from .services.google_oauth import (
    exchange_code_for_token,
    fetch_userinfo,
    GoogleOAuthError,
)

User = get_user_model()


class GoogleOAuthLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")
        code_verifier = request.data.get("code_verifier")  # optional (PKCE)

        if not code or not redirect_uri:
            return Response(
                {"detail": "code and redirect_uri are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_data = exchange_code_for_token(code, redirect_uri, code_verifier)
            access_token = token_data.get("access_token")
            if not access_token:
                return Response({"detail": "no access_token from google"}, status=400)

            profile = fetch_userinfo(access_token)

        except GoogleOAuthError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Google userinfo fields: sub, email, email_verified, name, picture, etc.
        sub = profile.get("sub")
        email = profile.get("email")
        if not sub:
            return Response({"detail": "google sub missing"}, status=400)

        # 계정 매핑(운영용):
        # 1) provider+sub로 유일하게 식별
        # 2) email은 표시/연락용 
        user, created = User.objects.get_or_create(
            provider="google",
            provider_sub=sub,
            defaults={
                "username": f"google_{sub[:16]}",
                "email": email or "",
            },
        )
        # 이메일이 새로 들어오면 업데이트
        if email and user.email != email:
            user.email = email
            user.save(update_fields=["email"])

        # watson 서비스에서 JWT 발급
        refresh = RefreshToken.for_user(user)
        res = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": MeSerializer(user).data,
            "created": created,
        }
        return Response(res, status=200)
