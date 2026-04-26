from __future__ import annotations

from django.db import connections
from django.http import JsonResponse
from django.utils import timezone


def health_check(_request):
    database_status = "ok"
    overall_status = "ok"

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        database_status = "error"
        overall_status = "error"
        return JsonResponse(
            {
                "status": overall_status,
                "service": "verimarka-backend",
                "database": database_status,
                "timestamp": timezone.now().isoformat(),
                "detail": str(exc),
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": overall_status,
            "service": "verimarka-backend",
            "database": database_status,
            "timestamp": timezone.now().isoformat(),
        }
    )
