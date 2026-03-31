import logging
import secrets
from datetime import timedelta

from django.utils import timezone
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import is_address, to_checksum_address
from web3 import Web3
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.blockchain_service import ContentBlockchainService

from .models import WalletConnectionChallenge, WalletLink
from .serializers import (
    WalletChallengeRequestSerializer,
    WalletLinkSerializer,
    WalletSummarySerializer,
    WalletVerifyRequestSerializer,
)

logger = logging.getLogger("wallets")

CHALLENGE_TTL_MINUTES = 10
VOTE_MINIMUM_NFT = 3


def _normalize_address(address: str) -> str:
    raw = (address or "").strip()
    if not raw or not is_address(raw):
        raise ValueError("유효한 지갑 주소를 입력해주세요.")
    return to_checksum_address(raw)


def _build_message(*, address: str, nonce: str, user_id: int) -> str:
    issued_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        "VeriMarka Wallet Connection\n"
        f"User ID: {user_id}\n"
        f"Address: {address}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}\n"
        "Purpose: Link this wallet to your VeriMarka account."
    )


class WalletLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet_link = getattr(request.user, "wallet_link", None)
        if wallet_link is None:
            return Response(
                {
                    "connected": False,
                    "address": None,
                    "chain_id": None,
                    "wallet_type": "",
                    "verified_at": None,
                },
                status=status.HTTP_200_OK,
            )
        return Response(WalletLinkSerializer(wallet_link).data, status=status.HTTP_200_OK)

    def delete(self, request):
        wallet_link = getattr(request.user, "wallet_link", None)
        if wallet_link is not None:
            logger.info(
                "wallet.unlink.success user_id=%s address=%s",
                request.user.id,
                wallet_link.address,
            )
            wallet_link.delete()
        return Response({"message": "지갑 연결이 해제되었습니다."}, status=status.HTTP_200_OK)


class WalletSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet_link = getattr(request.user, "wallet_link", None)
        if wallet_link is None:
            payload = {
                "connected": False,
                "address": None,
                "chain_id": None,
                "wallet_type": "",
                "network_name": "Sepolia",
                "nft_count": None,
                "vote_minimum": VOTE_MINIMUM_NFT,
                "vote_eligible": False,
                "lookup_status": "not_connected",
                "lookup_error": None,
            }
            return Response(WalletSummarySerializer(payload).data, status=status.HTTP_200_OK)

        nft_count = None
        network_name = "Sepolia"
        lookup_status = "ok"
        lookup_error = None
        try:
            blockchain = ContentBlockchainService._create_client()
            nft_count = int(
                blockchain.contract.functions.balanceOf(
                    Web3.to_checksum_address(wallet_link.address)
                ).call()
            )
            effective_chain_id = wallet_link.chain_id or getattr(blockchain, "chain_id", None)
            network_name = ContentBlockchainService.NETWORK_NAME_BY_CHAIN_ID.get(
                effective_chain_id,
                f"Chain {effective_chain_id}" if effective_chain_id else "Sepolia",
            )
        except Exception as exc:
            logger.warning(
                "wallet.summary.balance_lookup_failed user_id=%s address=%s error=%s",
                request.user.id,
                wallet_link.address,
                exc,
            )
            lookup_status = "failed"
            lookup_error = "NFT 보유 수량을 조회하지 못했습니다. 잠시 후 다시 시도해주세요."

        payload = {
            "connected": True,
            "address": wallet_link.address,
            "chain_id": wallet_link.chain_id,
            "wallet_type": wallet_link.wallet_type,
            "network_name": network_name,
            "nft_count": nft_count,
            "vote_minimum": VOTE_MINIMUM_NFT,
            "vote_eligible": lookup_status == "ok" and nft_count is not None and nft_count >= VOTE_MINIMUM_NFT,
            "lookup_status": lookup_status,
            "lookup_error": lookup_error,
        }
        return Response(WalletSummarySerializer(payload).data, status=status.HTTP_200_OK)


class WalletConnectChallengeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WalletChallengeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            address = _normalize_address(serializer.validated_data["address"])
        except ValueError as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        nonce = secrets.token_hex(16)
        message = _build_message(address=address, nonce=nonce, user_id=request.user.id)
        expires_at = timezone.now() + timedelta(minutes=CHALLENGE_TTL_MINUTES)

        WalletConnectionChallenge.objects.filter(
            user=request.user,
            used_at__isnull=True,
        ).update(used_at=timezone.now())

        challenge = WalletConnectionChallenge.objects.create(
            user=request.user,
            address=address,
            nonce=nonce,
            message=message,
            expires_at=expires_at,
        )

        logger.info(
            "wallet.challenge.created user_id=%s address=%s challenge_id=%s expires_at=%s",
            request.user.id,
            address,
            challenge.id,
            expires_at.isoformat(),
        )

        return Response(
            {
                "address": address,
                "message": message,
                "nonce": nonce,
                "expires_at": expires_at,
            },
            status=status.HTTP_200_OK,
        )


class WalletConnectVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WalletVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            address = _normalize_address(serializer.validated_data["address"])
        except ValueError as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        signature = (serializer.validated_data.get("signature") or "").strip()
        if not signature:
            return Response({"message": "지갑 서명이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        challenge = WalletConnectionChallenge.objects.filter(
            user=request.user,
            address=address,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at").first()

        if challenge is None:
            return Response(
                {"message": "지갑 연결 요청이 만료되었습니다. 다시 시도해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            recovered_address = Account.recover_message(
                encode_defunct(text=challenge.message),
                signature=signature,
            )
            recovered_address = _normalize_address(recovered_address)
        except Exception:
            return Response(
                {"message": "서명 검증에 실패했습니다. 다시 시도해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recovered_address != address:
            return Response(
                {"message": "현재 선택한 지갑과 서명한 지갑 주소가 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conflict_link = WalletLink.objects.filter(address=address).exclude(user=request.user).first()
        if conflict_link is not None:
            return Response(
                {"message": "이미 다른 계정에 연결된 지갑 주소입니다."},
                status=status.HTTP_409_CONFLICT,
            )

        verified_at = timezone.now()
        wallet_link, _ = WalletLink.objects.update_or_create(
            user=request.user,
            defaults={
                "address": address,
                "chain_id": serializer.validated_data.get("chain_id"),
                "wallet_type": serializer.validated_data.get("wallet_type", ""),
                "verified_at": verified_at,
            },
        )

        challenge.used_at = verified_at
        challenge.save(update_fields=["used_at"])

        logger.info(
            "wallet.link.success user_id=%s address=%s chain_id=%s wallet_type=%s",
            request.user.id,
            address,
            wallet_link.chain_id,
            wallet_link.wallet_type,
        )

        return Response(WalletLinkSerializer(wallet_link).data, status=status.HTTP_200_OK)
