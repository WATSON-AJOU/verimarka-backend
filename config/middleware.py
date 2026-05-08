from __future__ import annotations

import re
import uuid

from .logging import request_id_context, response_id_context

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalize_request_id(value: str | None) -> str:
    if not value:
        return uuid.uuid4().hex
    value = value.strip()
    if REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex


class RequestIdMiddleware:
    header_name = "HTTP_X_REQUEST_ID"
    request_header_name = "X-Request-Id"
    response_header_name = "X-Response-Id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = normalize_request_id(request.META.get(self.header_name))
        response_id = uuid.uuid4().hex
        request_token = request_id_context.set(request_id)
        response_token = response_id_context.set(response_id)
        request.request_id = request_id
        request.response_id = response_id

        try:
            response = self.get_response(request)
        finally:
            request_id_context.reset(request_token)
            response_id_context.reset(response_token)

        response[self.request_header_name] = request_id
        response[self.response_header_name] = response_id
        return response
