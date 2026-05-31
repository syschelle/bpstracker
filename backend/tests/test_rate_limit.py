from app.rate_limit import FixedWindowRateLimiter


def test_fixed_window_rate_limiter_blocks_after_limit() -> None:
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.check('client') is None
    assert limiter.check('client') is None
    assert limiter.check('client') is not None


def test_fixed_window_rate_limiter_clear_resets_key() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)

    assert limiter.check('client') is None
    assert limiter.check('client') is not None
    limiter.clear('client')
    assert limiter.check('client') is None
