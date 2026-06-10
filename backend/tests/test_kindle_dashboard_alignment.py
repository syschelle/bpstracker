from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.kindle_display import _today_energy_mix
from app.models import Device, DeviceType, Measurement
from app.routers.measurements import _local_day_bounds


def test_local_day_bounds_use_configured_timezone() -> None:
    now = datetime(2026, 6, 1, 22, 30, tzinfo=timezone.utc)  # 00:30 on June 2 in Europe/Berlin

    start, end = _local_day_bounds(now, 'Europe/Berlin')

    assert start == datetime(2026, 6, 1, 22, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)


def test_kindle_today_energy_mix_respects_configured_device_channel() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    tz = ZoneInfo('Europe/Berlin')
    start = datetime.now(tz).replace(hour=8, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    with SessionLocal() as db:
        grid = Device(
            name='Grid',
            host='192.168.1.10',
            device_type=DeviceType.shelly_3em_gen1,
            purpose='grid',
            channel=1,
        )
        db.add(grid)
        db.flush()
        # Unconfigured channel 0 would add 1.0 kWh if it was counted. The Kindle
        # path must apply the same channel filter as the dashboard summary.
        db.add(Measurement(timestamp=start, device_id=grid.id, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1', energy_import_wh=1000))
        db.add(Measurement(timestamp=start + timedelta(hours=1), device_id=grid.id, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1', energy_import_wh=2000))
        db.add(Measurement(timestamp=start, device_id=grid.id, source_type='shelly_3em_gen1_emeter', channel=1, phase='L2', energy_import_wh=5000))
        db.add(Measurement(timestamp=start + timedelta(hours=1), device_id=grid.id, source_type='shelly_3em_gen1_emeter', channel=1, phase='L2', energy_import_wh=5400))
        db.commit()

        imported_kwh, solar_kwh = _today_energy_mix(db, 'Europe/Berlin')

    assert imported_kwh == 0.4
    assert solar_kwh is None
