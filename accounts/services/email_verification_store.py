import hashlib
from datetime import datetime

import redis
from django.conf import settings
from django.utils import timezone

from accounts.services.fake_redis import FakeRedis

EMAIL_VERIFY_TTL_SECONDS = 180
EMAIL_VERIFY_DAILY_LIMIT = 3
EMAIL_VERIFY_MAX_FAIL_COUNT = 5


class EmailVerificationStoreError(Exception):
    pass


def _redis_client() -> redis.Redis:
    if getattr(settings, "USE_FAKE_REDIS", False):
        return FakeRedis()

    redis_url = settings.REDIS_URL
    if not redis_url:
        raise EmailVerificationStoreError("REDIS_URL이 설정되지 않았습니다.")
    if redis_url == "fakeredis://":
        return FakeRedis()
    return redis.Redis.from_url(redis_url, decode_responses=True)


def _code_key(user_id: int, email: str) -> str:
    return f"email_verify:code:{user_id}:{email}"


def _fail_key(user_id: int, email: str) -> str:
    return f"email_verify:fail:{user_id}:{email}"


def _daily_key(user_id: int, date: datetime) -> str:
    return f"email_verify:daily:{user_id}:{date.strftime('%Y%m%d')}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def get_daily_count(user_id: int) -> int:
    client = _redis_client()
    value = client.get(_daily_key(user_id, timezone.localtime()))
    return int(value or 0)


def increment_daily_count(user_id: int) -> int:
    client = _redis_client()
    key = _daily_key(user_id, timezone.localtime())
    count = client.incr(key)
    if count == 1:
        client.expire(key, 60 * 60 * 24)
    return int(count)


def store_code(user_id: int, email: str, code: str) -> None:
    client = _redis_client()
    client.setex(_code_key(user_id, email), EMAIL_VERIFY_TTL_SECONDS, hash_code(code))
    client.delete(_fail_key(user_id, email))


def get_code_hash(user_id: int, email: str) -> str | None:
    client = _redis_client()
    return client.get(_code_key(user_id, email))


def get_fail_count(user_id: int, email: str) -> int:
    client = _redis_client()
    return int(client.get(_fail_key(user_id, email)) or 0)


def increment_fail_count(user_id: int, email: str) -> int:
    client = _redis_client()
    key = _fail_key(user_id, email)
    count = client.incr(key)
    if count == 1:
        client.expire(key, EMAIL_VERIFY_TTL_SECONDS)
    return int(count)


def delete_code(user_id: int, email: str) -> None:
    client = _redis_client()
    client.delete(_code_key(user_id, email))
    client.delete(_fail_key(user_id, email))
