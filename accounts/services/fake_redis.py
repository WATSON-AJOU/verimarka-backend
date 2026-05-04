import time
from threading import RLock


class FakeRedis:
    _lock = RLock()
    _store: dict[str, tuple[str, float | None]] = {}

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    def get(self, key: str):
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at is not None and expires_at <= time.time():
                self._store.pop(key, None)
                return None
            return value

    def incr(self, key: str):
        with self._lock:
            value = int(self.get(key) or 0) + 1
            _, expires_at = self._store.get(key, ("", None))
            self._store[key] = (str(value), expires_at)
            return value

    def expire(self, key: str, seconds: int):
        with self._lock:
            if key not in self._store:
                return False
            value, _ = self._store[key]
            self._store[key] = (value, time.time() + seconds)
            return True

    def setex(self, key: str, seconds: int, value: str):
        with self._lock:
            self._store[key] = (value, time.time() + seconds)
            return True

    def delete(self, key: str):
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
            return int(existed)

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._store.clear()
