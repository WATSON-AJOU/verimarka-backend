from __future__ import annotations

import uuid

from .logging import request_id_context


class RequestIdMiddleware:
    header_name = "HTTP_X_REQUEST_ID"
    response_header_name = "X-Request-Id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.header_name) or uuid.uuid4().hex
        token = request_id_context.set(request_id)
        request.request_id = request_id

        try:
            response = self.get_response(request)
        finally:
            request_id_context.reset(token)

        response[self.response_header_name] = request_id
        return response
