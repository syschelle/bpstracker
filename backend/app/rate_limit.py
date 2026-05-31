from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status


@dataclass
class _Bucket:
    count: int
    reset_at: float


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    def check(self, key: str) -> int | None:
        now = time.time()
        with self._lock:
            # Opportunistic cleanup keeps the in-memory map bounded for normal use.
            expired_keys = [bucket_key for bucket_key, bucket in self._buckets.items() if bucket.reset_at <= now]
            for bucket_key in expired_keys[:100]:
                self._buckets.pop(bucket_key, None)

            bucket = self._buckets.get(key)
            if bucket is None or bucket.reset_at <= now:
                self._buckets[key] = _Bucket(count=1, reset_at=now + self.window_seconds)
                return None
            if bucket.count >= self.limit:
                return max(1, int(bucket.reset_at - now))
            bucket.count += 1
            return None

    def clear(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_rate_limit_key(request: Request) -> str:
    # Do not trust X-Forwarded-For by default. Deployments that need proxy-aware
    # rate limiting should terminate at a trusted reverse proxy that preserves the
    # real client address at the ASGI layer.
    return request.client.host if request.client else 'unknown'


def raise_rate_limited(retry_after_seconds: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail='Too many attempts. Please try again later.',
        headers={'Retry-After': str(retry_after_seconds)},
    )
