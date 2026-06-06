from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.routers import settings as settings_router
from app.routers.measurements import _clamp_live_window


def test_pi_zero_mode_sets_24h_effective_limits(monkeypatch):
    monkeypatch.setenv('PI_ZERO_2W_MODE', 'true')
    monkeypatch.delenv('LIVE_DATA_MAX_HOURS', raising=False)
    monkeypatch.delenv('RAW_RETENTION_HOURS', raising=False)
    get_settings.cache_clear()
    try:
        retention = settings_router._normalize_retention_value({'raw_retention_days': 30})
        assert retention.pi_zero_2w_mode is True
        assert retention.effective_raw_retention_hours == 24
        assert retention.live_data_max_hours == 24
    finally:
        get_settings.cache_clear()


def test_live_data_window_clamps_to_configured_hours(monkeypatch):
    monkeypatch.setenv('LIVE_DATA_MAX_HOURS', '24')
    monkeypatch.delenv('PI_ZERO_2W_MODE', raising=False)
    get_settings.cache_clear()
    try:
        end = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
        requested_start = end - timedelta(days=7)
        start, clamped_end = _clamp_live_window(requested_start, end)
        assert clamped_end == end
        assert start == end - timedelta(hours=24)
    finally:
        get_settings.cache_clear()
