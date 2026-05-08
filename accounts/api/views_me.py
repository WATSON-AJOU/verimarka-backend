from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api.serializers import (
    DisplayNameAvailabilitySerializer,
    MeSerializer,
    MeUpdateSerializer,
    NicknameAvailabilitySerializer,
)
from accounts.api.views_auth import blacklist_refresh_token
from accounts.models import User


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        serializer = MeUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(request.user).data, status=status.HTTP_200_OK)


class WithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        blacklist_refresh_token(request.data.get("refresh"))
        request.user.soft_delete()
        return Response(
            {"message": "회원 탈퇴가 완료되었습니다."},
            status=status.HTTP_200_OK,
        )


class NicknameAvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = NicknameAvailabilitySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {
                    "available": False,
                    "message": serializer.errors["nickname"][0],
                },
                status=status.HTTP_200_OK,
            )

        nickname = serializer.validated_data["nickname"]
        exists = User.objects.filter(nickname=nickname).exists()
        return Response(
            {
                "available": not exists,
                "message": "사용 가능한 닉네임입니다."
                if not exists
                else "이미 사용 중인 닉네임입니다.",
            },
            status=status.HTTP_200_OK,
        )


class DisplayNameAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = DisplayNameAvailabilitySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {
                    "available": False,
                    "message": serializer.errors["display_name"][0],
                },
                status=status.HTTP_200_OK,
            )

        display_name = serializer.validated_data["display_name"]
        exists = (
            User.objects.filter(display_name=display_name)
            .exclude(id=request.user.id)
            .exists()
        )
        return Response(
            {
                "available": not exists,
                "message": "사용 가능한 표시명입니다."
                if not exists
                else "이미 사용 중인 표시명입니다.",
            },
            status=status.HTTP_200_OK,
        )
