from types import SimpleNamespace

from app.models import DevicePurpose, DeviceType
from app.simulation import simulated_latest


def test_simulated_shelly_3em_grid_device_matches_real_device_rows() -> None:
    device = SimpleNamespace(
        id=42,
        device_type=DeviceType.shelly_3em_gen1,
        purpose=DevicePurpose.grid,
        channel=None,
        is_active=True,
    )

    rows = simulated_latest('Europe/Berlin', [device])

    assert [(row.channel, row.phase) for row in rows] == [
        (0, 'L1'),
        (1, 'L2'),
        (2, 'L3'),
        (None, 'total'),
    ]
    assert all(row.source_type == 'shelly_3em_gen1_emeter' for row in rows[:3])
    assert rows[3].source_type == 'shelly_3em_gen1_total'
    assert all(row.voltage_v is not None for row in rows[:3])
    assert all(row.current_a is not None for row in rows[:3])
    assert rows[3].power_w == sum(row.power_w for row in rows[:3])


def test_simulated_shelly_3em_respects_configured_channel() -> None:
    device = SimpleNamespace(
        id=43,
        device_type=DeviceType.shelly_3em_gen1,
        purpose=DevicePurpose.grid,
        channel=1,
        is_active=True,
    )

    rows = simulated_latest('Europe/Berlin', [device])

    assert [(row.channel, row.phase, row.source_type) for row in rows] == [
        (1, 'L2', 'shelly_3em_gen1_emeter'),
    ]

from datetime import datetime, timezone

from app.simulation import simulated_history, simulated_values_at, solar_power_at


def test_simulated_pv_peak_caps_current_power() -> None:
    noon = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    low_peak = solar_power_at(noon, 300)
    high_peak = solar_power_at(noon, 1200)

    assert low_peak <= 300
    assert high_peak > low_peak


def test_simulated_values_respect_configured_pv_peak() -> None:
    noon = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    low = simulated_values_at(noon, 'Europe/Berlin', 300)
    high = simulated_values_at(noon, 'Europe/Berlin', 1200)

    assert low.solar_w <= 300
    assert high.solar_w > low.solar_w
    assert high.solar_today_kwh > low.solar_today_kwh


def test_simulated_history_respects_configured_pv_peak() -> None:
    start = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)

    low = simulated_history(start, end, 'Europe/Berlin', 3600, 300)
    high = simulated_history(start, end, 'Europe/Berlin', 3600, 1200)

    assert max(point.solar_power_w or 0 for point in low) <= 300
    assert max(point.solar_power_w or 0 for point in high) > max(point.solar_power_w or 0 for point in low)
