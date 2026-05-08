from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()
env.read_env(BASE_DIR / ".env.prod")

from .base import *  # noqa: E402,F403

SECRET_KEY = env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 32 or SECRET_KEY in {"change-me", "unsafe-secret-key"}:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong production secret.")

DEBUG = env.bool("DJANGO_DEBUG", default=False)
if DEBUG:
    raise ImproperlyConfigured("DJANGO_DEBUG must be False in production settings.")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must be set in production.")

DATABASES = {
    "default": {
        "ENGINE": env(
            "DB_ENGINE",
            default="django.db.backends.postgresql",
        ),
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT", default="5432"),
        "OPTIONS": {
            "sslmode": env("DB_SSLMODE", default="require"),
        },
    }
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
SECURE_REFERRER_POLICY = env(
    "DJANGO_SECURE_REFERRER_POLICY", default="strict-origin-when-cross-origin"
)
SECURE_CROSS_ORIGIN_OPENER_POLICY = env(
    "DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY", default="same-origin"
)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
