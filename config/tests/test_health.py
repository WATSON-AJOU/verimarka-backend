from unittest.mock import patch

from django.test import RequestFactory

from config.health import health_check


def test_health_check_hides_database_exception_detail(db):
    request = RequestFactory().get("/api/health/")

    with patch("config.health.connections") as mocked_connections:
        mocked_connections.__getitem__.side_effect = RuntimeError(
            "password=secret host=internal-db"
        )

        response = health_check(request)

    assert response.status_code == 503
    assert b"password=secret" not in response.content
    assert b"internal-db" not in response.content
    assert b"database check failed" in response.content
