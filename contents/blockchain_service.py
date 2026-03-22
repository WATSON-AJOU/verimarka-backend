import importlib.util
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from analysis.services import AIIntegrationError

from .models import Content
from .storage import S3StorageService


class ContentBlockchainService:
    _blockchain_class = None

    NETWORK_NAME_BY_CHAIN_ID = {
        11155111: "Sepolia",
        137: "Polygon",
        80002: "Polygon Amoy",
    }

    @classmethod
    def mint(cls, *, content: Content) -> Content:
        if content.decision != "allow":
            raise AIIntegrationError(
                error_code="INVALID_STATE",
                error_message="ALLOW 판정 콘텐츠만 NFT를 발행할 수 있습니다.",
                retryable=False,
                status_code=400,
                job_id=str(content.public_id),
            )

        watermark = content.watermark or {}
        if not watermark.get("applied"):
            raise AIIntegrationError(
                error_code="INVALID_STATE",
                error_message="워터마크 삽입이 완료된 콘텐츠만 NFT를 발행할 수 있습니다.",
                retryable=False,
                status_code=400,
                job_id=str(content.public_id),
            )

        existing_blockchain = content.blockchain or {}
        if existing_blockchain.get("minted") and existing_blockchain.get("tx_hash"):
            return content

        blockchain = cls._create_client()
        recipient_address = cls._resolve_recipient_address(blockchain)
        file_bytes = cls._load_watermarked_bytes(content)
        file_hash_bytes = blockchain.compute_file_hash_sha256(file_bytes)
        wm_id = cls._resolve_wm_id(content)
        token_uri = cls._build_token_uri(content)

        try:
            receipt = blockchain.mint_document(
                to=recipient_address,
                wm_id=wm_id,
                file_hash=file_hash_bytes,
                token_uri=token_uri,
                is_suspicious=False,
            )
            verification = blockchain.verify_document(wm_id)
            token_info = (
                blockchain.get_document_info(verification["token_id"])
                if verification.get("exists") and verification.get("token_id")
                else None
            )
        except Exception as exc:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_MINT_FAIL",
                error_message=str(exc) or "NFT 토큰 발행에 실패했습니다.",
                retryable=True,
                status_code=500,
                job_id=str(content.public_id),
            ) from exc

        chain_id = getattr(blockchain, "chain_id", None)
        minted_at = timezone.now()
        content.blockchain = {
            **existing_blockchain,
            "minted": True,
            "network_name": cls.NETWORK_NAME_BY_CHAIN_ID.get(chain_id, f"Chain {chain_id}" if chain_id else "Unknown"),
            "chain_id": chain_id,
            "contract_address": getattr(blockchain, "contract_address", ""),
            "recipient_address": recipient_address,
            "owner_address": verification.get("owner") or recipient_address,
            "wm_id": wm_id,
            "token_id": verification.get("token_id"),
            "status": verification.get("status") or "Approved",
            "verification_link": verification.get("verification_link"),
            "token_uri": token_uri,
            "file_hash": f"0x{file_hash_bytes.hex()}",
            "tx_hash": receipt.get("tx_hash"),
            "block_number": receipt.get("block_number"),
            "gas_used": receipt.get("gas_used"),
            "minted_at": minted_at.isoformat(),
            "minted_at_display": timezone.localtime(minted_at).strftime("%Y.%m.%d %H:%M"),
            "model_name": watermark.get("model") or "WAM",
            "model_version": watermark.get("model_version") or "v2.1.0",
            "document": token_info or {},
        }
        content.save(update_fields=["blockchain", "updated_at"])
        return content

    @classmethod
    def _create_client(cls):
        blockchain_class = cls._get_blockchain_class()
        try:
            return blockchain_class()
        except Exception as exc:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_CONFIG_ERROR",
                error_message=str(exc) or "블록체인 연결 설정이 올바르지 않습니다.",
                retryable=False,
                status_code=500,
            ) from exc

    @classmethod
    def _get_blockchain_class(cls):
        if cls._blockchain_class is not None:
            return cls._blockchain_class

        integration_root = Path(
            getattr(
                settings,
                "BLOCKCHAIN_INTEGRATION_ROOT",
                Path(settings.BASE_DIR).parent / "Blockchain" / "backend_integration",
            )
        ).resolve()
        blockchain_path = integration_root / "blockchain.py"

        if not blockchain_path.exists():
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_MODULE_NOT_FOUND",
                error_message=f"blockchain module not found: {blockchain_path}",
                retryable=False,
                status_code=500,
            )

        spec = importlib.util.spec_from_file_location("verimarka_blockchain_module", blockchain_path)
        if spec is None or spec.loader is None:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_MODULE_LOAD_FAIL",
                error_message=f"unable to load blockchain module: {blockchain_path}",
                retryable=False,
                status_code=500,
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls._blockchain_class = module.WatsonBlockchain
        return cls._blockchain_class

    @classmethod
    def _resolve_recipient_address(cls, blockchain) -> str:
        recipient = getattr(settings, "WATSON_RECIPIENT_ADDRESS", "") or ""
        if recipient:
            return recipient

        owner_address = blockchain.get_owner_address()
        if owner_address:
            return owner_address

        minter_address = blockchain.get_minter_address()
        if minter_address:
            return minter_address

        raise AIIntegrationError(
            error_code="BLOCKCHAIN_CONFIG_ERROR",
            error_message="NFT 수신 지갑 주소를 확인할 수 없습니다.",
            retryable=False,
            status_code=500,
        )

    @classmethod
    def _load_watermarked_bytes(cls, content: Content) -> bytes:
        watermark = content.watermark or {}
        output_path = watermark.get("output_path")
        output_key = watermark.get("output_key")
        output_url = watermark.get("output_url")

        if output_path and Path(output_path).exists():
            return Path(output_path).read_bytes()

        if output_key and S3StorageService.is_enabled():
            client = S3StorageService._get_client()
            obj = client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=output_key)
            return obj["Body"].read()

        if output_url and not str(output_url).startswith(("http://", "https://")):
            relative_path = str(output_url).replace(settings.MEDIA_URL, "", 1).lstrip("/")
            local_path = Path(settings.MEDIA_ROOT) / relative_path
            if local_path.exists():
                return local_path.read_bytes()

        if content.original_file and Path(content.original_file.path).exists():
            return Path(content.original_file.path).read_bytes()

        raise AIIntegrationError(
            error_code="FILE_NOT_FOUND",
            error_message="민팅에 사용할 이미지 파일을 찾을 수 없습니다.",
            retryable=False,
            status_code=500,
            job_id=str(content.public_id),
        )

    @classmethod
    def _resolve_wm_id(cls, content: Content) -> int:
        watermark = content.watermark or {}
        payload_id = watermark.get("payload_id")

        if isinstance(payload_id, int) and payload_id > 0:
            return payload_id

        if isinstance(payload_id, str) and payload_id.isdigit():
            payload_int = int(payload_id)
            if payload_int > 0:
                return payload_int

        seed = str(payload_id or content.public_id)
        return max(1, zlib.crc32(seed.encode("utf-8")) & 0xFFFFFFFF)

    @classmethod
    def _build_token_uri(cls, content: Content) -> str:
        watermark = content.watermark or {}
        output_url = watermark.get("output_url") or ""

        if output_url.startswith(("http://", "https://", "ipfs://", "s3://")):
            return output_url

        if output_url:
            base_url = getattr(settings, "VERIMARKA_PUBLIC_BASE_URL", "https://verimarka.com").rstrip("/")
            return f"{base_url}{output_url}"

        return f"{getattr(settings, 'VERIMARKA_PUBLIC_BASE_URL', 'https://verimarka.com').rstrip('/')}/history"
