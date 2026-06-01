from datetime import datetime, timezone

from app.models import Measurement
from app.routers.measurements import _is_grid_row
from app.energy_retention import delta_energy


def test_auto_grid_energy_rows_are_included_in_dashboard_balances() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        Measurement(timestamp=now, device_id=1, source_type='shelly_rpc_emdata', channel=0, phase='total', energy_import_wh=1000),
        Measurement(timestamp=now, device_id=1, source_type='shelly_rpc_emdata', channel=0, phase='total', energy_import_wh=1350),
        Measurement(timestamp=now, device_id=2, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1', energy_import_wh=5000),
        Measurement(timestamp=now, device_id=2, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1', energy_import_wh=5400),
    ]
    purposes = {1: 'auto', 2: 'auto'}

    grid_rows = [row for row in rows if _is_grid_row(row, purposes)]

    assert len(grid_rows) == 4
    assert delta_energy(grid_rows, 'energy_import_wh', None) == 750


def test_ignored_grid_energy_rows_are_excluded_from_dashboard_balances() -> None:
    row = Measurement(source_type='shelly_rpc_emdata', device_id=1, channel=0, phase='total', energy_import_wh=1000)

    assert _is_grid_row(row, {1: 'ignored'}) is False


def test_configured_device_channel_filters_latest_and_balance_rows() -> None:
    rows = [
        Measurement(device_id=1, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1'),
        Measurement(device_id=1, source_type='shelly_3em_gen1_emeter', channel=1, phase='L2'),
        Measurement(device_id=1, source_type='shelly_3em_gen1_total', channel=None, phase='total'),
        Measurement(device_id=2, source_type='shelly_rpc_switch', channel=1, phase=None),
        Measurement(device_id=2, source_type='shelly_rpc_switch', channel=0, phase=None),
    ]
    configs = {
        1: ('shelly_3em_gen1', 1),
        2: ('shelly_2pm_gen4', 1),
    }

    from app.routers.measurements import _measurement_matches_device_config

    visible = [row for row in rows if _measurement_matches_device_config(row, configs)]

    assert [(row.device_id, row.source_type, row.channel, row.phase) for row in visible] == [
        (1, 'shelly_3em_gen1_emeter', 1, 'L2'),
        (2, 'shelly_rpc_switch', 1, None),
    ]


def test_unconfigured_device_channel_keeps_all_shelly_3em_rows() -> None:
    rows = [
        Measurement(device_id=1, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1'),
        Measurement(device_id=1, source_type='shelly_3em_gen1_emeter', channel=1, phase='L2'),
        Measurement(device_id=1, source_type='shelly_3em_gen1_emeter', channel=2, phase='L3'),
        Measurement(device_id=1, source_type='shelly_3em_gen1_total', channel=None, phase='total'),
    ]
    configs = {1: ('shelly_3em_gen1', None)}

    from app.routers.measurements import _measurement_matches_device_config

    assert [row for row in rows if _measurement_matches_device_config(row, configs)] == rows


def test_history_power_totals_integrate_displayed_range() -> None:
    from app.routers.measurements import _history_power_totals
    from app.schemas import HistoryPoint

    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    points = [
        HistoryPoint(timestamp=start, grid_power_w=500, solar_power_w=200, power_w=200),
        HistoryPoint(timestamp=start.replace(hour=13), grid_power_w=-100, solar_power_w=300, power_w=300),
        HistoryPoint(timestamp=start.replace(hour=14), grid_power_w=250, solar_power_w=400, power_w=400),
    ]

    totals = _history_power_totals(points)

    assert totals.imported_kwh == 0.75
    assert totals.exported_kwh == 0.1
    assert totals.solar_kwh == 0.9


def test_raw_history_rows_keeps_newest_rows_when_limited() -> None:
    from datetime import timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models import Device, DeviceType
    from app.routers.measurements import _raw_history_rows

    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    with SessionLocal() as db:
        device = Device(name='Grid', host='192.168.1.10', device_type=DeviceType.shelly_3em_gen1, purpose='grid')
        db.add(device)
        db.flush()
        for index in range(10):
            db.add(Measurement(
                timestamp=start + timedelta(minutes=index),
                device_id=device.id,
                source_type='shelly_3em_gen1_total',
                total_power_w=float(index),
            ))
        db.commit()

        rows = _raw_history_rows(db, start, start + timedelta(minutes=9), limit=3)

    assert [row.total_power_w for row in rows] == [7.0, 8.0, 9.0]
    assert [row.timestamp.replace(tzinfo=timezone.utc) if row.timestamp.tzinfo is None else row.timestamp for row in rows] == [
        start + timedelta(minutes=7),
        start + timedelta(minutes=8),
        start + timedelta(minutes=9),
    ]
