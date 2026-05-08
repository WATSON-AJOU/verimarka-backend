from django.conf import settings
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings

REFRESH_COOKIE_NAME = "verimarka_refresh_token"


def _refresh_cookie_name() -> str:
    return getattr(settings, "JWT_REFRESH_COOKIE_NAME", REFRESH_COOKIE_NAME)


def _refresh_cookie_path() -> str:
    return getattr(settings, "JWT_REFRESH_COOKIE_PATH", "/api/")


def _refresh_cookie_secure() -> bool:
    return getattr(settings, "JWT_REFRESH_COOKIE_SECURE", not settings.DEBUG)


def get_refresh_token_from_request(request) -> str | None:
    return request.data.get("refresh") or request.COOKIES.get(_refresh_cookie_name())


def set_refresh_cookie(response: Response, refresh_token: str) -> Response:
    response.set_cookie(
        _refresh_cookie_name(),
        refresh_token,
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=_refresh_cookie_path(),
        secure=_refresh_cookie_secure(),
        httponly=True,
        samesite=getattr(settings, "JWT_REFRESH_COOKIE_SAMESITE", "Lax"),
    )
    response["Cache-Control"] = "no-store"
    return response


def clear_refresh_cookie(response: Response) -> Response:
    response.delete_cookie(
        _refresh_cookie_name(),
        path=_refresh_cookie_path(),
        samesite=getattr(settings, "JWT_REFRESH_COOKIE_SAMESITE", "Lax"),
    )
    response["Cache-Control"] = "no-store"
    return response
