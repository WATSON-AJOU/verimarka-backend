import re
from pathlib import Path

from rest_framework import serializers
from django.utils import timezone

MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
}
ALLOWED_IMAGE_EXTENSIONS = {ext for extensions in ALLOWED_IMAGE_MIME_TYPES.values() for ext in extensions}
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
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError("JPG 또는 PNG 파일만 업로드할 수 있습니다.")

    normalized_mime_type = (mime_type or "").lower()
    allowed_extensions = ALLOWED_IMAGE_MIME_TYPES.get(normalized_mime_type)
    if allowed_extensions and extension not in allowed_extensions:
        raise serializers.ValidationError("파일 확장자와 MIME 타입이 일치하지 않습니다.")

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
        stem = "image"

    max_stem_length = 120 - len(extension)
    safe_stem = stem[:max_stem_length].rstrip(" ._") or "image"
    return f"{safe_stem}{extension}"


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
    return upload
