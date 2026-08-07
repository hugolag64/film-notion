"""Small in-process sliding-window limiter for single-instance auth endpoints."""

from collections import deque
from dataclasses import dataclass, field
from math import ceil
import time
from typing import Deque, Dict, Optional


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    remaining: int = 0


@dataclass
class _Bucket:
    attempts: Deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int, block_seconds: int):
        if max_attempts < 1 or window_seconds < 1 or block_seconds < 1:
            raise ValueError("rate limiter values must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._buckets: Dict[str, _Bucket] = {}

    def check(self, key: str, now: Optional[float] = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        bucket = self._buckets.setdefault(key, _Bucket())
        if bucket.blocked_until > current:
            return RateLimitDecision(False, max(1, ceil(bucket.blocked_until - current)), 0)
        bucket.blocked_until = 0.0
        cutoff = current - self.window_seconds
        while bucket.attempts and bucket.attempts[0] <= cutoff:
            bucket.attempts.popleft()
        if len(bucket.attempts) >= self.max_attempts:
            bucket.blocked_until = current + self.block_seconds
            bucket.attempts.clear()
            return RateLimitDecision(False, self.block_seconds, 0)
        bucket.attempts.append(current)
        return RateLimitDecision(True, 0, self.max_attempts - len(bucket.attempts))

    def clear(self, key: str) -> None:
        self._buckets.pop(key, None)
