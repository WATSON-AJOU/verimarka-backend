from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_media_path(value: str | None) -> Path | None:
    if not value:
        return None

    parsed = urlsplit(str(value).strip())
    if parsed.scheme or parsed.netloc:
        return None

    media_url = (
        settings.MEDIA_URL
        if settings.MEDIA_URL.startswith("/")
        else f"/{settings.MEDIA_URL}"
    )
    path = unquote(parsed.path)
    if not path.startswith(media_url):
        return None

    relative_path = path.removeprefix(media_url).lstrip("/")
    if not relative_path:
        return None

    media_root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (media_root / relative_path).resolve()
    if not _is_relative_to(candidate, media_root):
        return None
    return candidate


def resolve_existing_media_path(value: str | None) -> Path | None:
    candidate = resolve_media_path(value)
    if candidate is None or not candidate.exists():
        return None
    return candidate
