from .base import *
import environ

env = environ.Env()
env.read_env(BASE_DIR / ".env.dev")

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# React dev 서버 허용
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 개발 편의: 인증 없이도 확인 가능한 엔드포인트가 필요하면 뷰에서 permission 조절
