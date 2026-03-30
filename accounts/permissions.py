from rest_framework.permissions import BasePermission


class IsPhoneVerified(BasePermission):
    message = "전화번호 인증이 필요합니다."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return request.user.phone_verified


class IsWalletLinked(BasePermission):
    message = "지갑 연결이 필요합니다."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return bool(getattr(request.user, "wallet_link", None))
