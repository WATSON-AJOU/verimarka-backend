from pathlib import Path
import environ

# base.py import 전에 .env.dev를 먼저 읽어서 os.environ에 주입
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
env = environ.Env()
env.read_env(BASE_DIR / ".env.dev")

from .base import *  # noqa: E402,F403

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
