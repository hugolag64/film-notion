from backend.core.rate_limit import RateLimiter


def test_rate_limiter_blocks_after_max_attempts_and_expires_block():
    limiter = RateLimiter(max_attempts=2, window_seconds=60, block_seconds=30)

    assert limiter.check("user", now=100.0).allowed is True
    assert limiter.check("user", now=101.0).allowed is True
    blocked = limiter.check("user", now=102.0)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 30

    assert limiter.check("user", now=132.0).allowed is True


def test_rate_limiter_clear_removes_previous_failures():
    limiter = RateLimiter(max_attempts=1, window_seconds=60, block_seconds=30)

    assert limiter.check("user", now=100.0).allowed is True
    assert limiter.check("user", now=101.0).allowed is False
    limiter.clear("user")
    assert limiter.check("user", now=102.0).allowed is True
