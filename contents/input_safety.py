import re
from pathlib import Path

from django.utils import timezone
from rest_framework import serializers

MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
}
ALLOWED_DOCUMENT_MIME_TYPES = {
    "application/pdf": {".pdf"},
    "application/msword": {".doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        ".docx"
    },
}
ALLOWED_UPLOAD_MIME_TYPES = {
    **ALLOWED_IMAGE_MIME_TYPES,
    **ALLOWED_DOCUMENT_MIME_TYPES,
}
ALLOWED_IMAGE_EXTENSIONS = {
    ext for extensions in ALLOWED_IMAGE_MIME_TYPES.values() for ext in extensions
}
ALLOWED_DOCUMENT_EXTENSIONS = {
    ext for extensions in ALLOWED_DOCUMENT_MIME_TYPES.values() for ext in extensions
}
ALLOWED_UPLOAD_EXTENSIONS = {
    ext for extensions in ALLOWED_UPLOAD_MIME_TYPES.values() for ext in extensions
}
GENERIC_UPLOAD_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
MIME_TYPE_BY_EXTENSION = {
    ext: mime_type
    for mime_type, extensions in ALLOWED_UPLOAD_MIME_TYPES.items()
    for ext in extensions
}
FILE_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "application/pdf": (b"%PDF-",),
    "application/msword": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        b"PK\x03\x04",
        b"PK\x05\x06",
        b"PK\x07\x08",
    ),
}
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_MULTISPACE_RE = re.compile(r"\s+")
_SAFE_FILE_STEM_RE = re.compile(r"[^0-9A-Za-z가-힣._()\- ]+")


def normalize_uploaded_filename(name: str, *, mime_type: str | None = None) -> str:
    raw_name = (name or "").strip().replace("\\", "/")
    basename = raw_name.rsplit("/", 1)[-1]
    basename = _CONTROL_CHARS_RE.sub("", basename)
    basename = _MULTISPACE_RE.sub(" ", basename).strip()
    basename = basename.lstrip(".")

    if not basename:
        raise serializers.ValidationError("파일명이 올바르지 않습니다.")

    extension = Path(basename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise serializers.ValidationError(
            "JPG, PNG, PDF, DOC, DOCX 파일만 업로드할 수 있습니다."
        )

    normalized_mime_type = (mime_type or "").lower()
    allowed_extensions = ALLOWED_UPLOAD_MIME_TYPES.get(normalized_mime_type)
    if allowed_extensions and extension not in allowed_extensions:
        raise serializers.ValidationError(
            "파일 확장자와 MIME 타입이 일치하지 않습니다."
        )

    stem = Path(basename).stem.strip()
    if not stem:
        raise serializers.ValidationError("파일명이 올바르지 않습니다.")

    max_stem_length = 120 - len(extension)
    display_stem = stem[:max_stem_length].rstrip(" .") or "image"
    return f"{display_stem}{extension}"


def sanitize_uploaded_filename(name: str, *, mime_type: str | None = None) -> str:
    basename = normalize_uploaded_filename(name, mime_type=mime_type)
    extension = Path(basename).suffix.lower()
    stem = Path(basename).stem
    stem = _SAFE_FILE_STEM_RE.sub("_", stem)
    stem = _MULTISPACE_RE.sub(" ", stem).strip(" ._")
    if stem.lower() in {"image", "images"}:
        stem = timezone.localtime().strftime("upload_%Y%m%d_%H%M%S")
    if not stem:
        stem = "upload"

    max_stem_length = 120 - len(extension)
    safe_stem = stem[:max_stem_length].rstrip(" ._") or "image"
    return f"{safe_stem}{extension}"


def validate_file_signature(upload, mime_type: str) -> None:
    signatures = FILE_SIGNATURES.get(mime_type)
    if not signatures:
        return

    max_length = max(len(signature) for signature in signatures)
    try:
        position = upload.tell()
    except (AttributeError, OSError):
        position = None

    try:
        header = upload.read(max_length)
    finally:
        try:
            upload.seek(position or 0)
        except (AttributeError, OSError):
            pass

    if not any(header.startswith(signature) for signature in signatures):
        raise serializers.ValidationError("파일 내용과 형식이 일치하지 않습니다.")


def validate_uploaded_image_file(upload):
    mime_type = (getattr(upload, "content_type", "") or "").lower()
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise serializers.ValidationError("JPG 또는 PNG 파일만 업로드할 수 있습니다.")

    file_size = getattr(upload, "size", 0) or 0
    if file_size <= 0:
        raise serializers.ValidationError("비어 있는 파일은 업로드할 수 없습니다.")
    if file_size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("파일 크기는 20MB 이하만 가능합니다.")

    normalize_uploaded_filename(getattr(upload, "name", ""), mime_type=mime_type)
    validate_file_signature(upload, mime_type)
    return upload


def validate_uploaded_content_file(upload):
    mime_type = (getattr(upload, "content_type", "") or "").lower()
    normalize_uploaded_filename(getattr(upload, "name", ""), mime_type=mime_type)
    if (
        mime_type not in ALLOWED_UPLOAD_MIME_TYPES
        and mime_type not in GENERIC_UPLOAD_MIME_TYPES
    ):
        raise serializers.ValidationError(
            "JPG, PNG, PDF, DOC, DOCX 파일만 업로드할 수 있습니다."
        )

    file_size = getattr(upload, "size", 0) or 0
    if file_size <= 0:
        raise serializers.ValidationError("비어 있는 파일은 업로드할 수 없습니다.")
    if file_size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("파일 크기는 20MB 이하만 가능합니다.")

    resolved_mime_type = resolve_upload_mime_type(upload)
    validate_file_signature(upload, resolved_mime_type)
    return upload


def resolve_upload_mime_type(upload) -> str:
    mime_type = (getattr(upload, "content_type", "") or "").lower()
    if mime_type in ALLOWED_UPLOAD_MIME_TYPES:
        return mime_type

    if mime_type in GENERIC_UPLOAD_MIME_TYPES:
        filename = normalize_uploaded_filename(
            getattr(upload, "name", ""), mime_type=mime_type
        )
        extension = Path(filename).suffix.lower()
        inferred_mime_type = MIME_TYPE_BY_EXTENSION.get(extension)
        if inferred_mime_type:
            return inferred_mime_type

    raise serializers.ValidationError("지원하지 않는 파일 형식입니다.")


def resolve_content_type_from_mime(mime_type: str | None) -> str:
    normalized = (mime_type or "").lower()
    if normalized in ALLOWED_IMAGE_MIME_TYPES:
        return "image"
    if normalized in ALLOWED_DOCUMENT_MIME_TYPES:
        return "document"
    raise serializers.ValidationError("지원하지 않는 파일 형식입니다.")
