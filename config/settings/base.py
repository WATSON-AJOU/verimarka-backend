from pathlib import Path

import environ
from corsheaders.defaults import default_headers

from config.logging import build_logging_config
from config.sentry import init_sentry


def _find_project_base() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "manage.py").exists():
            return parent
    return current.parent.parent.parent


def _default_ai_model_root(base_dir: Path) -> str:
    local_child = base_dir / "WATSON_WM" / "img_guard"
    if local_child.exists():
        return str(local_child)

    sibling_child = base_dir.parent / "WATSON_WM" / "img_guard"
    return str(sibling_child)


BASE_DIR = _find_project_base()

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)

# .env 파일 로드는 dev.py / prod.py 에서 수행
SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-secret-key")
DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "accounts",
    "analysis",
    "contents",
    "logs",
    "reviews",
    "tokens",
    "wallets",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "config.middleware.RequestIdMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": env("DB_NAME", default=str(BASE_DIR / "db.sqlite3")),
        "USER": env("DB_USER", default=""),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default=""),
        "PORT": env("DB_PORT", default=""),
    }
}

# PostgreSQL일 때만 OPTIONS 추가
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": env("DB_SSLMODE", default="require"),
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("DRF_AUTH_THROTTLE_RATE", default="10/min"),
        "oauth": env("DRF_OAUTH_THROTTLE_RATE", default="20/min"),
    },
    "EXCEPTION_HANDLER": "config.exceptions.verimarka_exception_handler",
}

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-request-id",
]
CORS_ALLOW_CREDENTIALS = True

JWT_REFRESH_COOKIE_NAME = env(
    "JWT_REFRESH_COOKIE_NAME", default="verimarka_refresh_token"
)
JWT_REFRESH_COOKIE_PATH = env("JWT_REFRESH_COOKIE_PATH", default="/api/")
JWT_REFRESH_COOKIE_SECURE = env.bool("JWT_REFRESH_COOKIE_SECURE", default=not DEBUG)
JWT_REFRESH_COOKIE_SAMESITE = env("JWT_REFRESH_COOKIE_SAMESITE", default="Lax")

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")
GOOGLE_TOKEN_URI = env(
    "GOOGLE_TOKEN_URI",
    default="https://oauth2.googleapis.com/token",
)
GOOGLE_USERINFO_URI = env(
    "GOOGLE_USERINFO_URI",
    default="https://openidconnect.googleapis.com/v1/userinfo",
)

KAKAO_REST_API_KEY = env("KAKAO_REST_API_KEY", default="")
KAKAO_CLIENT_SECRET = env("KAKAO_CLIENT_SECRET", default="")

APPLE_TEAM_ID = env("APPLE_TEAM_ID", default="")
APPLE_SERVICES_ID = env("APPLE_SERVICES_ID", default="")
APPLE_KEY_ID = env("APPLE_KEY_ID", default="")
APPLE_PRIVATE_KEY = env("APPLE_PRIVATE_KEY", default="")
APPLE_TOKEN_URI = env(
    "APPLE_TOKEN_URI",
    default="https://appleid.apple.com/auth/token",
)
APPLE_JWKS_URI = env(
    "APPLE_JWKS_URI",
    default="https://appleid.apple.com/auth/keys",
)
OAUTH_ALLOWED_REDIRECT_URIS = env.list(
    "OAUTH_ALLOWED_REDIRECT_URIS",
    default=[
        "https://verimarka.com/auth/google/callback",
        "https://verimarka.com/auth/kakao/callback",
        "https://verimarka.com/auth/apple/callback",
        "https://admin.verimarka.com/auth/google/callback",
        "https://admin.verimarka.com/auth/kakao/callback",
        "https://admin.verimarka.com/auth/apple/callback",
        "http://localhost:5173/auth/google/callback",
        "http://localhost:5173/auth/kakao/callback",
        "http://localhost:5173/auth/apple/callback",
        "http://localhost:5174/auth/google/callback",
        "http://localhost:5174/auth/kakao/callback",
        "http://localhost:5174/auth/apple/callback",
    ],
)

SOLAPI_API_KEY = env("SOLAPI_API_KEY", default="")
SOLAPI_API_SECRET = env("SOLAPI_API_SECRET", default="")
SOLAPI_SENDER = env("SOLAPI_SENDER", default="")
REDIS_URL = env("REDIS_URL", default="")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Seoul"
CELERY_TASK_DEFAULT_QUEUE = "default"
AWS_SES_REGION = env("AWS_SES_REGION", default=env("AWS_REGION", default=""))
AWS_SES_SENDER_EMAIL = env(
    "AWS_SES_SENDER_EMAIL",
    default=env("SES_FROM_EMAIL", default=""),
)

AI_MODEL_ROOT = env(
    "AI_MODEL_ROOT",
    default=_default_ai_model_root(BASE_DIR),
)
BLOCKCHAIN_INTEGRATION_ROOT = env(
    "BLOCKCHAIN_INTEGRATION_ROOT",
    default=str(BASE_DIR.parent / "Blockchain" / "backend_integration"),
)
VERIMARKA_PUBLIC_BASE_URL = env(
    "VERIMARKA_PUBLIC_BASE_URL", default="https://verimarka.com"
)
WATSON_RECIPIENT_ADDRESS = env("WATSON_RECIPIENT_ADDRESS", default="")
BLOCKCHAIN_EVENT_SYNC_SECRET = env("BLOCKCHAIN_EVENT_SYNC_SECRET", default="")
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env(
    "SENTRY_ENVIRONMENT", default="development" if DEBUG else "production"
)
SENTRY_RELEASE = env("SENTRY_RELEASE", default="")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

AWS_S3_ENABLED = env.bool("AWS_S3_ENABLED", default=False)
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
AWS_DEFAULT_REGION = env("AWS_DEFAULT_REGION", default="")
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="")
AWS_S3_USE_SSL = env.bool("AWS_S3_USE_SSL", default=True)
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="virtual")
AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=3600)
CONTENT_ORIGINAL_PREFIX = env("CONTENT_ORIGINAL_PREFIX", default="original")
CONTENT_CANDIDATE_PREFIX = env("CONTENT_CANDIDATE_PREFIX", default="candidate")
CONTENT_RESULT_PREFIX = env("CONTENT_RESULT_PREFIX", default="result")
CONTENT_VERIFY_PREFIX = env("CONTENT_VERIFY_PREFIX", default="verify")
DOC_DEFAULT_TYPE = env("DOC_DEFAULT_TYPE", default="labor_contract_std_v1")
DOC_RENDER_DPI = env.int("DOC_RENDER_DPI", default=220)
DOC_MAX_PAGES = env.int("DOC_MAX_PAGES", default=5)
DOC_OCR_TIMEOUT_SEC = env.int("DOC_OCR_TIMEOUT_SEC", default=30)
CLOVA_OCR_INVOKE_URL = env("CLOVA_OCR_INVOKE_URL", default="")
CLOVA_OCR_SECRET = env("CLOVA_OCR_SECRET", default="")
S3_PREFIX_DOC_REGISTER_REQUEST = env(
    "S3_PREFIX_DOC_REGISTER_REQUEST", default="document/register_request"
)
S3_PREFIX_DOC_VERIFY_REQUEST = env(
    "S3_PREFIX_DOC_VERIFY_REQUEST", default="document/verify_request"
)
S3_PREFIX_DOC_WATERMARK_RESULT = env(
    "S3_PREFIX_DOC_WATERMARK_RESULT", default="document/watermarked"
)
S3_PREFIX_DOC_PREVIEW = env("S3_PREFIX_DOC_PREVIEW", default="document/preview")
S3_PREFIX_DOC_OCR_RAW = env("S3_PREFIX_DOC_OCR_RAW", default="document/ocr_raw")
S3_PREFIX_DOC_REJECTED = env("S3_PREFIX_DOC_REJECTED", default="document/rejected")
DJANGO_LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO").upper()

LOGGING = build_logging_config(default_level=DJANGO_LOG_LEVEL)

init_sentry(
    dsn=SENTRY_DSN,
    environment=SENTRY_ENVIRONMENT,
    release=SENTRY_RELEASE or None,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
)
