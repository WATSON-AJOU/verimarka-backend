from __future__ import annotations

from contextvars import ContextVar


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter:
    def filter(self, record) -> bool:
        record.request_id = request_id_context.get("-")
        return True


def build_logging_config(*, default_level: str = "INFO") -> dict:
    app_logger_names = (
        "accounts",
        "analysis",
        "config",
        "contents",
        "logs",
        "reviews",
        "tokens",
        "wallets",
    )

    logger_config = {
        "django": {
            "handlers": ["console"],
            "level": default_level,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": default_level,
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": default_level,
            "propagate": False,
        },
    }

    for logger_name in app_logger_names:
        logger_config[logger_name] = {
            "handlers": ["console"],
            "level": default_level,
            "propagate": False,
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": "config.logging.RequestIdFilter",
            },
        },
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s:%(lineno)d %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "filters": ["request_id"],
                "formatter": "standard",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": default_level,
        },
        "loggers": logger_config,
    }
