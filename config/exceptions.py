import logging
from typing import Any
from collections.abc import Mapping, Sequence

from rest_framework import status
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from analysis.services import AIIntegrationError


logger = logging.getLogger(__name__)

DEFAULT_SERVER_ERROR_MESSAGE = "서버 내부 오류가 발생했습니다."
REDACTED_KEYS = {"password", "token", "access", "refresh", "authorization", "secret", "signature"}


def verimarka_exception_handler(exc, context):
    request = context.get("request")
    request_snapshot = _build_request_snapshot(request)

    if isinstance(exc, AIIntegrationError):
        payload = exc.to_response().model_dump()
        payload["detail"] = exc.error_message
        response = Response(payload, status=exc.status_code)
        _attach_response_tracking_headers(response, request)
        _log_exception(
            logger.warning if exc.status_code < 500 else logger.error,
            "api.ai_integration_error",
            request_snapshot=request_snapshot,
            response_snapshot=_build_response_snapshot(response, payload),
            exc=exc,
            include_stack=False,
        )
        return response

    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data
        message = _extract_error_message(detail)
        payload = {
            "error_code": _resolve_error_code(exc, response.status_code),
            "error_message": message,
            "detail": message,
            "retryable": False,
        }

        if isinstance(detail, Mapping):
            payload.update(detail)
        payload["errors"] = detail

        response.data = payload
        _attach_response_tracking_headers(response, request)
        _log_exception(
            logger.warning if response.status_code < 500 else logger.error,
            "api.handled_exception",
            request_snapshot=request_snapshot,
            response_snapshot=_build_response_snapshot(response, payload),
            exc=exc,
            include_stack=False,
        )
        return response

    payload = {
        "error_code": "INTERNAL_SERVER_ERROR",
        "error_message": DEFAULT_SERVER_ERROR_MESSAGE,
        "detail": DEFAULT_SERVER_ERROR_MESSAGE,
        "retryable": False,
    }
    response = Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    _attach_response_tracking_headers(response, request)
    _log_exception(
        logger.exception,
        "api.unhandled_exception",
        request_snapshot=request_snapshot,
        response_snapshot=_build_response_snapshot(response, payload),
        exc=exc,
        include_stack=True,
    )
    return response


def _resolve_error_code(exc, status_code: int) -> str:
    if isinstance(exc, ValidationError):
        return "INVALID_INPUT"

    default_code = getattr(exc, "default_code", None)
    if isinstance(default_code, str) and default_code:
        return default_code.upper()

    return f"HTTP_{status_code}"


def _extract_error_message(detail) -> str:
    if isinstance(detail, ErrorDetail):
        return str(detail)

    if isinstance(detail, str):
        return detail

    if isinstance(detail, Mapping):
        if "detail" in detail:
            return _extract_error_message(detail["detail"])
        for value in detail.values():
            message = _extract_error_message(value)
            if message:
                return message
        return DEFAULT_SERVER_ERROR_MESSAGE

    if isinstance(detail, Sequence) and not isinstance(detail, (str, bytes, bytearray)):
        for item in detail:
            message = _extract_error_message(item)
            if message:
                return message

    return DEFAULT_SERVER_ERROR_MESSAGE


def _attach_response_tracking_headers(response: Response, request) -> None:
    request_id = getattr(request, "request_id", None)
    response_id = getattr(request, "response_id", None)
    if request_id:
        response["X-Request-Id"] = request_id
    if response_id:
        response["X-Response-Id"] = response_id


def _log_exception(
    log_method,
    event: str,
    *,
    request_snapshot: dict[str, Any],
    response_snapshot: dict[str, Any],
    exc: Exception,
    include_stack: bool,
) -> None:
    log_method(
        "%s request=%s response=%s exc_type=%s exc_message=%s",
        event,
        request_snapshot,
        response_snapshot,
        exc.__class__.__name__,
        str(exc),
        exc_info=include_stack,
    )


def _build_request_snapshot(request) -> dict[str, Any]:
    if request is None:
        return {}

    data = None
    try:
        if hasattr(request, "data"):
            data = request.data
    except Exception:
        data = "<unavailable>"

    return {
        "request_id": getattr(request, "request_id", None),
        "response_id": getattr(request, "response_id", None),
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        "query_params": _truncate_value(_sanitize_value(getattr(request, "query_params", {}))),
        "data": _truncate_value(_sanitize_value(data)),
        "content_type": getattr(request, "content_type", None),
        "user_id": getattr(getattr(request, "user", None), "id", None),
        "client_ip": _extract_client_ip(request),
        "user_agent": _truncate_value((getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT")),
    }


def _build_response_snapshot(response: Response, payload: Any) -> dict[str, Any]:
    return {
        "status_code": getattr(response, "status_code", None),
        "error_code": payload.get("error_code") if isinstance(payload, Mapping) else None,
        "detail": _truncate_value(_sanitize_value(payload.get("detail") if isinstance(payload, Mapping) else payload)),
    }


def _extract_client_ip(request) -> str | None:
    meta = getattr(request, "META", {}) or {}
    forwarded_for = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return meta.get("REMOTE_ADDR")


def _sanitize_value(value: Any):
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in REDACTED_KEYS:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, ErrorDetail):
        return str(value)
    return value


def _truncate_value(value: Any, limit: int = 1000):
    rendered = str(value)
    if len(rendered) <= limit:
        return value
    return f"{rendered[:limit]}...<truncated>"
