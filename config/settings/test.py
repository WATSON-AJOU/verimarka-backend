from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key-for-verimarka-jwt-signing"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test.sqlite3",  # noqa: F405
    }
}

MIGRATION_MODULES = {
    "accounts": None,
    "analysis": None,
    "contents": None,
    "logs": None,
    "operations": None,
    "reviews": None,
    "tokens": None,
    "wallets": None,
}

MEDIA_ROOT = BASE_DIR / "test_media"  # noqa: F405
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

REDIS_URL = "fakeredis://"
USE_FAKE_REDIS = True

CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True

SENTRY_DSN = ""
AWS_S3_ENABLED = False
BYPASS_WALLET_LINK_PERMISSION = True
