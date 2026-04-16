import logging
from collections.abc import Mapping, Sequence

from rest_framework import status
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from analysis.services import AIIntegrationError


logger = logging.getLogger(__name__)

DEFAULT_SERVER_ERROR_MESSAGE = "서버 내부 오류가 발생했습니다."


def verimarka_exception_handler(exc, context):
    request = context.get("request")

    if isinstance(exc, AIIntegrationError):
        payload = exc.to_response().model_dump()
        payload["detail"] = exc.error_message
        return Response(payload, status=exc.status_code)

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
        return response

    logger.exception(
        "api.unhandled_exception method=%s path=%s user_id=%s",
        getattr(request, "method", None),
        getattr(request, "path", None),
        getattr(getattr(request, "user", None), "id", None),
        exc_info=exc,
    )
    return Response(
        {
            "error_code": "INTERNAL_SERVER_ERROR",
            "error_message": DEFAULT_SERVER_ERROR_MESSAGE,
            "detail": DEFAULT_SERVER_ERROR_MESSAGE,
            "retryable": False,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


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
