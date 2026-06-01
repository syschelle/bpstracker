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
