import tempfile
import zlib
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from analysis.contracts import GuardRequestV1
from analysis.services import AIIntegrationError, AnalysisGuardService
from analysis.watermark_services import WatermarkAIService

from .blockchain_service import ContentBlockchainService
from .models import Content
from .services import ContentRegistrationService
from .storage import S3StorageService


class ContentVerificationService:
    @classmethod
    def verify_image(cls, *, user, upload) -> dict:
        temp_path = cls._write_temp_file(upload)
        try:
            source_input = cls._build_source_input(temp_path=temp_path, upload=upload)
            detect_response = WatermarkAIService.detect(
                {
                    "job_id": f"verify-{timezone.now().timestamp()}",
                    "input": {
                        **source_input,
                        "filename": upload.name,
                        "mime_type": getattr(upload, "content_type", "") or "application/octet-stream",
                    },
                    "options": {
                        "model": "wam",
                        "threshold": 0.5,
                    },
                }
            )

            detect_result = detect_response.get("result", {})
            if detect_response.get("success") and detect_result.get("detected"):
                verified_payload = cls._build_verified_result(
                    user=user,
                    upload=upload,
                    temp_path=temp_path,
                    detect_result=detect_result,
                )
                if verified_payload:
                    return verified_payload

            return cls._build_candidate_result(user=user, upload=upload, source_input=source_input)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    @classmethod
    def _build_verified_result(cls, *, user, upload, temp_path: Path, detect_result: dict) -> dict | None:
        wm_id = cls._resolve_wm_id(detect_result.get("payload_id"))
        blockchain = ContentBlockchainService._create_client()

        try:
            verification = blockchain.verify_document(wm_id)
        except Exception as exc:
            raise AIIntegrationError(
                error_code="BLOCKCHAIN_VERIFY_FAIL",
                error_message=str(exc) or "블록체인 검증 조회에 실패했습니다.",
                retryable=True,
                status_code=500,
            ) from exc

        if not verification.get("exists"):
            return None

        content = (
            Content.objects.filter(
                decision="allow",
                blockchain__wm_id=wm_id,
            )
            .select_related("owner")
            .order_by("-created_at")
            .first()
        )

        token_id = verification.get("token_id")
        token_info = blockchain.get_document_info(token_id) if token_id else {}
        image_url = cls._resolve_content_image_url(content)

        return {
            "outcome": "verified",
            "headline_badge": "VERIFIED",
            "headline_title": "워터마크 검증에 성공했습니다.",
            "headline_subtitle": "검출된 워터마크와 블록체인 토큰을 연결했습니다.",
            "uploaded": {
                "file_name": upload.name,
                "file_size": upload.size,
                "preview_url": image_url,
                "verified_at": timezone.localtime().strftime("%Y.%m.%d %H:%M"),
                "verifier_name": getattr(user, "display_name", "") or getattr(user, "nickname", "") or "게스트",
            },
            "detect": {
                "detected": True,
                "confidence": detect_result.get("confidence"),
                "bit_accuracy": detect_result.get("bit_accuracy"),
                "payload_id": detect_result.get("payload_id"),
                "model": detect_result.get("model"),
                "model_version": detect_result.get("model_version"),
            },
            "blockchain": {
                "token_id": token_id,
                "owner_address": verification.get("owner"),
                "status": verification.get("status"),
                "verification_link": verification.get("verification_link"),
                "network_name": ContentBlockchainService.NETWORK_NAME_BY_CHAIN_ID.get(
                    getattr(blockchain, "chain_id", None),
                    f"Chain {getattr(blockchain, 'chain_id', '')}".strip(),
                ),
                "content_hash": f"0x{blockchain.compute_file_hash_sha256(temp_path.read_bytes()).hex()}",
                "transaction_hash": (content.blockchain or {}).get("tx_hash") if content else None,
                "minted_at": (content.blockchain or {}).get("minted_at_display") if content else None,
                "document": cls._json_safe(token_info),
            },
        }

    @classmethod
    def _build_candidate_result(cls, *, user, upload, source_input: dict) -> dict:
        guard_request = GuardRequestV1(
            job_id=f"verify-fallback-{timezone.now().timestamp()}",
            mode="register",
            content_type="image",
            input=[
                {
                    **source_input,
                    "filename": upload.name,
                    "mime_type": getattr(upload, "content_type", "") or "application/octet-stream",
                }
            ],
            meta={
                "user_id": str(getattr(user, "id", "")),
                "verify_filename": upload.name,
            },
            options={},
        )
        response = AnalysisGuardService.run_guard_v1(guard_request.model_dump())

        selected_match, candidate_content, candidate_preview_url = cls._select_displayable_candidate(response)
        candidate_owner = None
        candidate_registered_at = None
        candidate_file_name = None

        if candidate_content:
            candidate_owner = (
                candidate_content.owner.display_name
                or candidate_content.owner.nickname
                or candidate_content.owner.username
                or candidate_content.owner.email
            )
            candidate_registered_at = timezone.localtime(candidate_content.created_at).strftime("%Y.%m.%d %H:%M")
            candidate_file_name = candidate_content.original_filename

        return {
            "outcome": "candidate",
            "headline_badge": "FAILED",
            "headline_title": "워터마크 검출에 실패했습니다.",
            "headline_subtitle": "서비스 내 유사 이미지 후보를 탐색한 결과를 확인하세요.",
            "uploaded": {
                "file_name": upload.name,
                "file_size": upload.size,
                "preview_url": None,
                "verified_at": timezone.localtime().strftime("%Y.%m.%d %H:%M"),
                "verifier_name": getattr(user, "display_name", "") or getattr(user, "nickname", "") or "게스트",
            },
            "detect": {
                "detected": False,
                "status_label": "실패",
            },
            "candidate": {
                "preview_url": candidate_preview_url,
                "file_name": candidate_file_name or selected_match.get("db_file"),
                "owner_name": candidate_owner or "artist@verimarka.com",
                "registered_at": candidate_registered_at or "2026.03.18 16:05",
                "cosine": selected_match.get("cosine"),
                "phash_dist": selected_match.get("phash_dist"),
                "threshold": 8,
                "summary": (
                    "서비스 DB 유사 이미지 후보 1건 발견"
                    if selected_match
                    else "유사 이미지 후보를 찾지 못했습니다."
                ),
            },
        }

    @classmethod
    def _select_displayable_candidate(cls, response) -> tuple[dict, Content | None, str | None]:
        matches: list[dict] = []
        if response.top_match:
            matches.append(response.top_match.model_dump())
        matches.extend(candidate.model_dump() for candidate in response.candidates)

        seen_keys: set[str] = set()
        for match in matches:
            db_key = match.get("db_key") or ""
            if db_key in seen_keys:
                continue
            if db_key:
                seen_keys.add(db_key)

            candidate_content = ContentRegistrationService._find_content_by_db_key(db_key)
            preview_url = cls._resolve_match_preview_url(match, candidate_content)
            if preview_url:
                return match, candidate_content, preview_url

        return {}, None, None

    @classmethod
    def _write_temp_file(cls, upload) -> Path:
        suffix = Path(upload.name).suffix or ".png"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        with temp_file as f:
            for chunk in upload.chunks():
                f.write(chunk)
        return Path(temp_file.name)

    @classmethod
    def _build_source_input(cls, *, temp_path: Path, upload) -> dict[str, str]:
        if not S3StorageService.is_enabled():
            return {"url": str(temp_path.resolve())}

        key = S3StorageService.build_content_key(
            owner_id=0,
            content_public_id=f"verify-{zlib.crc32(upload.name.encode('utf-8')) & 0xFFFFFFFF}",
            filename=upload.name,
            stage="verify",
        )
        S3StorageService.upload_file(
            local_path=str(temp_path),
            key=key,
            content_type=getattr(upload, "content_type", "") or "application/octet-stream",
        )
        return {
            "url": S3StorageService.generate_presigned_get_url(key=key),
            "s3_key": key,
            "s3_uri": S3StorageService.build_s3_uri(key=key),
        }

    @classmethod
    def _resolve_wm_id(cls, payload_id: str | None) -> int:
        if isinstance(payload_id, str) and payload_id.isdigit():
            return int(payload_id)
        seed = str(payload_id or "verify-fallback")
        return max(1, zlib.crc32(seed.encode("utf-8")) & 0xFFFFFFFF)

    @classmethod
    def _resolve_content_image_url(cls, content: Content | None) -> str | None:
        if not content:
            return None

        watermark = content.watermark or {}
        output_key = watermark.get("output_key")
        output_url = watermark.get("output_url")

        if output_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=output_key)

        if output_url:
            if output_url.startswith(("http://", "https://")):
                return output_url
            base_url = getattr(settings, "VERIMARKA_PUBLIC_BASE_URL", "https://verimarka.com").rstrip("/")
            return f"{base_url}{output_url}"

        if content.original_storage_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=content.original_storage_key)

        if content.original_file:
            return content.original_file.url

        return None

    @classmethod
    def _resolve_match_preview_url(cls, match: dict, content: Content | None) -> str | None:
        content_url = cls._resolve_content_image_url(content)
        if content_url:
            return content_url

        db_key = match.get("db_key")
        if db_key and S3StorageService.is_enabled():
            try:
                return S3StorageService.generate_presigned_get_url(key=db_key)
            except Exception:
                return None

        return None

    @classmethod
    def _json_safe(cls, value):
        if isinstance(value, bytes):
            return f"0x{value.hex()}"
        if isinstance(value, dict):
            return {key: cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        return value
