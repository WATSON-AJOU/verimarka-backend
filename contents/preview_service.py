import logging
import tempfile
from pathlib import Path

import fitz
from django.conf import settings

from contents.input_safety import sanitize_uploaded_filename
from contents.models import Content
from contents.storage import S3StorageService

logger = logging.getLogger(__name__)

PDF_MIME_TYPE = "application/pdf"
DOCUMENT_PREVIEW_MIME_TYPE = "image/png"


def is_pdf_file(*, mime_type: str | None = None, filename: str = "") -> bool:
    normalized = (mime_type or "").lower()
    return normalized == PDF_MIME_TYPE or filename.lower().endswith(".pdf")


def render_pdf_first_page_thumbnail(
    *, source_path: Path, output_path: Path, zoom: float = 2.0
) -> None:
    with fitz.open(str(source_path)) as document:
        if document.page_count < 1:
            raise ValueError("PDF has no pages.")
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pixmap.save(output_path)


def create_pdf_first_page_preview(
    *,
    source_path: Path,
    owner_id: int,
    content_public_id: str,
    filename: str,
) -> dict:
    safe_name = sanitize_uploaded_filename(filename, mime_type=PDF_MIME_TYPE)
    preview_name = f"{Path(safe_name).stem or 'document'}_page1.png"

    try:
        if S3StorageService.is_enabled():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                preview_path = Path(temp_file.name)
            try:
                render_pdf_first_page_thumbnail(
                    source_path=source_path, output_path=preview_path
                )
                key = S3StorageService.build_content_key(
                    owner_id=owner_id,
                    content_public_id=content_public_id,
                    filename=preview_name,
                    stage=settings.S3_PREFIX_DOC_PREVIEW,
                )
                S3StorageService.upload_file(
                    local_path=str(preview_path),
                    key=key,
                    content_type=DOCUMENT_PREVIEW_MIME_TYPE,
                )
                return {
                    "preview_key": key,
                    "preview_url": S3StorageService.generate_presigned_get_url(key=key),
                    "preview_mime_type": DOCUMENT_PREVIEW_MIME_TYPE,
                }
            finally:
                preview_path.unlink(missing_ok=True)

        destination_dir = (
            Path(settings.MEDIA_ROOT)
            / "contents"
            / str(owner_id)
            / str(content_public_id)
            / "preview"
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / preview_name
        render_pdf_first_page_thumbnail(
            source_path=source_path, output_path=destination_path
        )
        return {
            "preview_url": f"{settings.MEDIA_URL.rstrip('/')}/contents/{owner_id}/{content_public_id}/preview/{preview_name}",
            "preview_path": str(destination_path),
            "preview_mime_type": DOCUMENT_PREVIEW_MIME_TYPE,
        }
    except Exception:
        logger.exception(
            "contents.preview.pdf_thumbnail_failed owner_id=%s content_id=%s filename=%s",
            owner_id,
            content_public_id,
            filename,
        )
        return {}


def resolve_preview_asset_url(asset: dict | None, request=None) -> str | None:
    if not asset:
        return None

    key = asset.get("preview_key")
    if key and S3StorageService.is_enabled():
        return S3StorageService.generate_presigned_get_url(key=key)

    url = asset.get("preview_url")
    if not url:
        return None

    path = asset.get("preview_path")
    if path:
        try:
            if not Path(path).exists():
                return None
        except (TypeError, OSError):
            return None

    if url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url) if request else url


def resolve_content_document_preview_url(
    content: Content, request=None, *, prefer_watermark: bool = False
) -> str | None:
    metadata = content.document_metadata or {}
    asset = metadata.get("watermark_preview") if prefer_watermark else None
    preview_url = resolve_preview_asset_url(asset, request=request)
    if preview_url:
        return preview_url
    return resolve_preview_asset_url(metadata.get("preview"), request=request)
