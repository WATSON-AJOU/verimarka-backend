from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def init_sentry(
    *,
    dsn: str | None,
    environment: str,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
    send_default_pii: bool = True,
) -> None:
    normalized_dsn = (dsn or "").strip()
    if not normalized_dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ModuleNotFoundError:
        logger.warning("sentry.init_skipped_missing_sdk environment=%s", environment)
        return

    logging_integration = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR,
    )

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
        request_data = (event.get("request") or {}).get("data")
        if isinstance(request_data, dict):
            for key in list(request_data.keys()):
                lowered = str(key).lower()
                if any(token in lowered for token in ("password", "token", "secret", "authorization", "signature")):
                    request_data[key] = "***REDACTED***"
        return event

    sentry_sdk.init(
        dsn=normalized_dsn,
        environment=environment,
        release=release,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            logging_integration,
        ],
        traces_sample_rate=traces_sample_rate,
        send_default_pii=send_default_pii,
        before_send=before_send,
    )

    logger.info("sentry.initialized environment=%s traces_sample_rate=%s", environment, traces_sample_rate)


def capture_sentry_message(
    message: str,
    *,
    level: str = "warning",
    tags: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        import sentry_sdk
    except ModuleNotFoundError:
        return

    with sentry_sdk.push_scope() as scope:
        for key, value in (tags or {}).items():
            scope.set_tag(key, value)
        for key, value in (extra or {}).items():
            scope.set_extra(key, value)
        sentry_sdk.capture_message(message, level=level)
