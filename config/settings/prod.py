from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
env = environ.Env()
env.read_env(BASE_DIR / ".env.prod")

from .base import *  # noqa: E402,F403

DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# 운영은 도메인 확정 후 넣기
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# 보안 옵션(운영에서 https 적용 시)
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
