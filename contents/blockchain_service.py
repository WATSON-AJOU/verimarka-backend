import importlib.util
import logging
import sys
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from analysis.services import AIIntegrationError

from .models import Content
from .storage import S3StorageService


logger = logging.getLogger(__name__)


class ContentBlockchainService:
    _blockchain_class = None
    _vector_upsert_callable = None
    REVIEW_THRESHOLD = 0.75

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
        if (
            existing_blockchain.get("mint_kind") == "content"
            and existing_blockchain.get("minted")
            and existing_blockchain.get("tx_hash")
        ):
            previous_blockchain = cls._json_safe(existing_blockchain)
            content = cls._ensure_vector_upserted(content=content)
            if content.blockchain != previous_blockchain:
                content.save(update_fields=["blockchain", "updated_at"])
            return content

        blockchain = cls._create_client()
        recipient_address = cls._resolve_recipient_address(blockchain, content=content)
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
        logger.info(
            "contents.blockchain.mint_prepare content_id=%s recipient_address=%s wallet_linked=%s",
            content.public_id,
            recipient_address,
            bool(getattr(content.owner, "wallet_link", None)),
        )
        content.blockchain = {
            **existing_blockchain,
            "minted": True,
            "mint_kind": "content",
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
            "document": cls._json_safe(token_info or {}),
        }
        content = cls._ensure_vector_upserted(content=content)
        content.save(update_fields=["blockchain", "updated_at"])
        return content

    @classmethod
    def start_review_vote(cls, *, content: Content) -> Content:
        if content.decision != "review":
            raise AIIntegrationError(
                error_code="INVALID_STATE",
                error_message="REVIEW 판정 콘텐츠만 커뮤니티 검증을 시작할 수 있습니다.",
                retryable=False,
                status_code=400,
                job_id=str(content.public_id),
            )

        existing_blockchain = content.blockchain or {}
        existing_vote = existing_blockchain.get("vote") or {}
        if existing_blockchain.get("mint_kind") == "review_vote" and existing_blockchain.get("token_id"):
            return cls.sync_review_vote(content=content)

        blockchain = cls._create_client()
        recipient_address = cls._resolve_recipient_address(blockchain, content=content)
        file_bytes = cls._load_original_bytes(content)
        file_hash_bytes = blockchain.compute_file_hash_sha256(file_bytes)
        wm_id = cls._resolve_wm_id(content)
        token_uri = cls._build_token_uri(content)
        file_hash_hex = f"0x{file_hash_bytes.hex()}"

        try:
            file_hash_used = blockchain.is_file_hash_used(file_hash_bytes)
        except Exception as exc:
            logger.warning(
                "contents.blockchain.review_vote_hash_check_failed content_id=%s wm_id=%s error=%s",
                content.public_id,
                wm_id,
                exc,
            )
            file_hash_used = False

        logger.info(
            "contents.blockchain.review_vote_start_prepare content_id=%s wm_id=%s file_hash=%s file_hash_used=%s token_uri=%s",
            content.public_id,
            wm_id,
            file_hash_hex,
            file_hash_used,
            token_uri,
        )

        if file_hash_used:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_VOTE_ALREADY_REGISTERED",
                error_message="이미 등록된 파일 해시라서 커뮤니티 검증 투표를 새로 생성할 수 없습니다.",
                retryable=False,
                status_code=409,
                job_id=str(content.public_id),
            )

        try:
            receipt = blockchain.mint_document(
                to=recipient_address,
                wm_id=wm_id,
                file_hash=file_hash_bytes,
                token_uri=token_uri,
                is_suspicious=True,
            )
        except Exception as exc:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_VOTE_START_FAIL",
                error_message=str(exc) or "커뮤니티 검증 투표 생성에 실패했습니다.",
                retryable=True,
                status_code=500,
                job_id=str(content.public_id),
            ) from exc

        content.blockchain = {
            **existing_blockchain,
            "minted": True,
            "mint_kind": "review_vote",
            "recipient_address": recipient_address,
            "wm_id": wm_id,
            "token_uri": token_uri,
            "file_hash": f"0x{file_hash_bytes.hex()}",
            "tx_hash": receipt.get("tx_hash"),
            "block_number": receipt.get("block_number"),
            "gas_used": receipt.get("gas_used"),
            "vote": {
                **existing_vote,
                "active": True,
            },
        }
        content.status = "review"
        content.next_action = "start_vote"
        content.save(update_fields=["blockchain", "status", "next_action", "updated_at"])
        return cls.sync_review_vote(content=content)

    @classmethod
    def sync_review_vote(cls, *, content: Content) -> Content:
        blockchain_data = content.blockchain or {}
        if blockchain_data.get("mint_kind") != "review_vote":
            raise AIIntegrationError(
                error_code="INVALID_STATE",
                error_message="커뮤니티 검증 투표가 아직 생성되지 않았습니다.",
                retryable=False,
                status_code=400,
                job_id=str(content.public_id),
            )

        blockchain = cls._create_client()
        wm_id = blockchain_data.get("wm_id") or cls._resolve_wm_id(content)

        try:
            verification = blockchain.verify_document(wm_id)
            if not verification.get("exists") or not verification.get("token_id"):
                raise AIIntegrationError(
                    error_code="BLOCKCHAIN_VOTE_NOT_FOUND",
                    error_message="생성된 커뮤니티 검증 토큰을 찾을 수 없습니다.",
                    retryable=True,
                    status_code=500,
                    job_id=str(content.public_id),
                )

            token_id = verification["token_id"]
            token_info = blockchain.get_document_info(token_id)
            end_time = token_info.get("end_time") or 0
            status_name = token_info.get("status") or verification.get("status") or "Pending"

            if status_name == "Pending" and end_time and end_time <= int(timezone.now().timestamp()):
                blockchain.finalize_status(token_id)
                verification = blockchain.verify_document(wm_id)
                token_info = blockchain.get_document_info(token_id)
                status_name = token_info.get("status") or verification.get("status") or "Pending"
        except AIIntegrationError:
            raise
        except Exception as exc:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_VOTE_SYNC_FAIL",
                error_message=str(exc) or "커뮤니티 검증 상태를 동기화하지 못했습니다.",
                retryable=True,
                status_code=500,
                job_id=str(content.public_id),
            ) from exc

        chain_id = getattr(blockchain, "chain_id", None)
        now = timezone.now()
        vote_payload = cls._build_vote_payload(content=content, token_id=token_id, status_name=status_name, token_info=token_info)
        minted_at_display = blockchain_data.get("minted_at_display") or timezone.localtime(now).strftime("%Y.%m.%d %H:%M")

        updated_blockchain = {
            **blockchain_data,
            "minted": True,
            "mint_kind": "review_vote",
            "network_name": cls.NETWORK_NAME_BY_CHAIN_ID.get(chain_id, f"Chain {chain_id}" if chain_id else "Unknown"),
            "chain_id": chain_id,
            "contract_address": getattr(blockchain, "contract_address", ""),
            "recipient_address": blockchain_data.get("recipient_address") or cls._resolve_recipient_address(blockchain, content=content),
            "owner_address": verification.get("owner") or blockchain_data.get("owner_address"),
            "wm_id": wm_id,
            "token_id": token_id,
            "status": verification.get("status") or status_name,
            "verification_link": verification.get("verification_link"),
            "token_uri": blockchain_data.get("token_uri") or cls._build_token_uri(content),
            "minted_at": blockchain_data.get("minted_at") or now.isoformat(),
            "minted_at_display": minted_at_display,
            "document": cls._json_safe(token_info or {}),
            "vote": vote_payload,
        }

        update_fields = ["blockchain", "updated_at"]
        content.blockchain = updated_blockchain

        if status_name == "Approved":
            content.status = "allow"
            content.decision = "allow"
            content.reason = "커뮤니티 검증 승인"
            content.next_action = "none"
            update_fields.extend(["status", "decision", "reason", "next_action"])
        elif status_name == "Rejected":
            content.status = "block"
            content.decision = "block"
            content.reason = "커뮤니티 검증 거절"
            content.next_action = "none"
            update_fields.extend(["status", "decision", "reason", "next_action"])
        else:
            content.status = "review"
            content.decision = "review"
            content.next_action = "start_vote"
            update_fields.extend(["status", "decision", "next_action"])

        content.save(update_fields=update_fields)
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
    def _ensure_vector_upserted(cls, *, content: Content) -> Content:
        blockchain_data = content.blockchain or {}
        vector_upsert = blockchain_data.get("vector_upsert") or {}
        if vector_upsert.get("success"):
            return content

        try:
            response = cls._upsert_watermarked_vector(content=content)
        except AIIntegrationError as exc:
            logger.warning(
                "contents.blockchain.vector_upsert_failed content_id=%s error_code=%s message=%s",
                content.public_id,
                exc.error_code,
                exc.error_message,
            )
            response = {
                "success": False,
                "reason": exc.error_message,
                "error_code": exc.error_code,
            }

        content.blockchain = {
            **blockchain_data,
            "vector_upsert": {
                **cls._json_safe(response),
                "updated_at": timezone.now().isoformat(),
            },
        }
        return content

    @classmethod
    def _upsert_watermarked_vector(cls, *, content: Content) -> dict[str, Any]:
        watermark = content.watermark or {}
        output_key = watermark.get("output_key")
        output_path = watermark.get("output_path")
        output_url = watermark.get("output_url")

        input_payload: dict[str, Any] = {
            "filename": content.original_filename,
            "mime_type": content.mime_type,
        }
        if output_key:
            input_payload["s3_key"] = output_key
            if S3StorageService.is_enabled():
                input_payload["s3_uri"] = S3StorageService.build_s3_uri(key=output_key)
                input_payload["url"] = S3StorageService.generate_presigned_get_url(key=output_key)
        elif output_path and Path(output_path).exists():
            input_payload["local_path"] = output_path
        elif output_url:
            input_payload["url"] = output_url
        else:
            raise AIIntegrationError(
                error_code="VECTOR_UPSERT_INPUT_MISSING",
                error_message="워터마크 결과 이미지를 찾을 수 없어 검색 인덱스에 반영할 수 없습니다.",
                retryable=True,
                status_code=500,
                job_id=str(content.public_id),
            )

        try:
            response = cls._get_vector_upsert_callable()(
                {
                    "job_id": f"mint-upsert-{content.public_id}",
                    "input": input_payload,
                    "s3_key": output_key,
                    "asset_url": input_payload.get("url"),
                    "file_name": content.original_filename,
                }
            )
        except Exception as exc:
            raise AIIntegrationError(
                error_code="VECTOR_UPSERT_FAIL",
                error_message=str(exc) or "pgvector upsert에 실패했습니다.",
                retryable=True,
                status_code=500,
                job_id=str(content.public_id),
            ) from exc

        payload = response.model_dump() if hasattr(response, "model_dump") else response
        if not payload.get("success"):
            raise AIIntegrationError(
                error_code="VECTOR_UPSERT_FAIL",
                error_message=payload.get("reason") or "pgvector upsert에 실패했습니다.",
                retryable=True,
                status_code=500,
                job_id=str(content.public_id),
            )
        return payload

    @classmethod
    def _get_vector_upsert_callable(cls):
        if cls._vector_upsert_callable is not None:
            return cls._vector_upsert_callable

        aimodel_root = cls._ensure_aimodel_path()
        persist_path = aimodel_root / "app" / "persist_service.py"

        if not persist_path.exists():
            raise AIIntegrationError(
                error_code="AI_MODULE_NOT_FOUND",
                error_message=f"persist_service module not found: {persist_path}",
                retryable=False,
                status_code=500,
            )

        spec = importlib.util.spec_from_file_location("verimarka_persist_module", persist_path)
        if spec is None or spec.loader is None:
            raise AIIntegrationError(
                error_code="AI_MODULE_LOAD_FAIL",
                error_message=f"unable to load persist_service module: {persist_path}",
                retryable=False,
                status_code=500,
            )

        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except ModuleNotFoundError as exc:
            raise AIIntegrationError(
                error_code="AI_DEPENDENCY_MISSING",
                error_message=str(exc),
                retryable=False,
                status_code=500,
            ) from exc

        cls._vector_upsert_callable = module.upsert_vector_embedding_v1
        return cls._vector_upsert_callable

    @classmethod
    def _ensure_aimodel_path(cls):
        aimodel_root = Path(
            getattr(
                settings,
                "AI_MODEL_ROOT",
                Path(settings.BASE_DIR).parent / "WATSON_WM" / "img_guard",
            )
        ).resolve()

        if not aimodel_root.exists():
            raise AIIntegrationError(
                error_code="AI_MODULE_NOT_FOUND",
                error_message=f"img_guard module not found: {aimodel_root}",
                retryable=False,
                status_code=500,
            )

        aimodel_root_str = str(aimodel_root)
        if aimodel_root_str not in sys.path:
            sys.path.insert(0, aimodel_root_str)
        return aimodel_root

    @classmethod
    def _resolve_recipient_address(cls, blockchain, *, content: Content) -> str:
        wallet_link = getattr(content.owner, "wallet_link", None)
        if wallet_link and wallet_link.address:
            return wallet_link.address

        raise AIIntegrationError(
            error_code="WALLET_NOT_LINKED",
            error_message="연동된 사용자 지갑 주소를 확인할 수 없습니다.",
            retryable=False,
            status_code=400,
            job_id=str(content.public_id),
        )

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, bytes):
            return f"0x{value.hex()}"
        if isinstance(value, dict):
            return {key: cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        return value

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
    def _load_original_bytes(cls, content: Content) -> bytes:
        if content.original_storage_key and S3StorageService.is_enabled():
            client = S3StorageService._get_client()
            obj = client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=content.original_storage_key)
            return obj["Body"].read()

        if content.original_file and Path(content.original_file.path).exists():
            return Path(content.original_file.path).read_bytes()

        raise AIIntegrationError(
            error_code="FILE_NOT_FOUND",
            error_message="커뮤니티 검증 생성에 사용할 원본 이미지를 찾을 수 없습니다.",
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
    def _build_vote_payload(cls, *, content: Content, token_id: int, status_name: str, token_info: dict[str, Any]) -> dict[str, Any]:
        upvotes = int(token_info.get("upvotes") or 0)
        downvotes = int(token_info.get("downvotes") or 0)
        started_at = cls._from_unix(token_info.get("timestamp"))
        end_time = cls._from_unix(token_info.get("end_time"))
        finalized_at = timezone.now() if status_name in {"Approved", "Rejected"} else None
        top_cosine = content.top_cosine if isinstance(content.top_cosine, (float, int)) else None
        threshold = cls.REVIEW_THRESHOLD
        return {
            "active": status_name == "Pending",
            "vote_id": f"VOTE-{token_id}",
            "status": status_name,
            "upvotes": upvotes,
            "downvotes": downvotes,
            "participant_count": upvotes + downvotes,
            "started_at": started_at.isoformat() if started_at else None,
            "started_at_display": cls._format_dt(started_at),
            "end_time": end_time.isoformat() if end_time else None,
            "end_time_display": cls._format_dt(end_time),
            "finalized_at": finalized_at.isoformat() if finalized_at else None,
            "finalized_at_display": cls._format_dt(finalized_at),
            "similarity_percent": round(float(top_cosine) * 100, 1) if top_cosine is not None else None,
            "threshold": threshold,
            "delta": round(float(top_cosine) - threshold, 4) if top_cosine is not None else None,
        }

    @classmethod
    def _from_unix(cls, value: Any):
        if not value:
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.get_current_timezone())

    @classmethod
    def _format_dt(cls, value) -> str | None:
        if not value:
            return None
        return timezone.localtime(value).strftime("%Y.%m.%d %H:%M")

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
