from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from ..models import User
from ..serializers import MeSerializer, MeUpdateSerializer


# 내정보조회
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
        request.user.soft_delete()
        return Response(
            {"message": "회원 탈퇴가 완료되었습니다."},
            status=status.HTTP_200_OK,
        )


class NicknameAvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        nickname = (request.query_params.get("nickname") or "").strip()

        if not nickname:
            return Response(
                {
                    "available": False,
                    "message": "닉네임을 입력해주세요.",
                },
                status=status.HTTP_200_OK,
            )

        if len(nickname) > 30:
            return Response(
                {
                    "available": False,
                    "message": "닉네임은 30자 이하로 입력해주세요.",
                },
                status=status.HTTP_200_OK,
            )

        exists = User.objects.filter(nickname=nickname).exists()
        return Response(
            {
                "available": not exists,
                "message": "사용 가능한 닉네임입니다." if not exists else "이미 사용 중인 닉네임입니다.",
            },
            status=status.HTTP_200_OK,
        )


class DisplayNameAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        display_name = (request.query_params.get("display_name") or "").strip()

        if not display_name:
            return Response(
                {
                    "available": False,
                    "message": "표시명을 입력해주세요.",
                },
                status=status.HTTP_200_OK,
            )

        if len(display_name) > 50:
            return Response(
                {
                    "available": False,
                    "message": "표시명은 50자 이하로 입력해주세요.",
                },
                status=status.HTTP_200_OK,
            )

        exists = User.objects.filter(display_name=display_name).exclude(id=request.user.id).exists()
        return Response(
            {
                "available": not exists,
                "message": "사용 가능한 표시명입니다." if not exists else "이미 사용 중인 표시명입니다.",
            },
            status=status.HTTP_200_OK,
        )
