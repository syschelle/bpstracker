"""v0.9.57: energy summaries stay correct without loading a day's raw payloads."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.energy_retention import (
    calculate_day_summary,
    cleanup_old_raw_measurements,
    delta_energy,
    energy_counter_edges,
    ensure_completed_daily_summaries,
)
from app.models import DailyEnergySummary, Device, Measurement


@pytest.fixture
def db():
    # Production uses PostgreSQL; the edge-reader also works on SQLite to make
    # value-parity regression tests fast and independent of an external server.
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with sessionmaker(bind=engine)() as session:
            yield session
    finally:
        engine.dispose()


def add_reading(db, device, timestamp, source, *, channel=None, phase=None, imported=None, exported=None):
    db.add(Measurement(
        timestamp=timestamp,
        device_id=device.id,
        source_type=source,
        channel=channel,
        phase=phase,
        energy_import_wh=imported,
        energy_export_wh=exported,
        raw_json={'large_raw_payload': 'X' * 3000},
    ))


def test_day_edge_counters_match_existing_delta_math_without_reading_json(db):
    grid = Device(name='Grid', host='192.0.2.1')
    solar = Device(name='Solar', host='192.0.2.2')
    db.add_all([grid, solar])
    db.flush()
    start = datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc)

    # Multiple independent phases and channels, missing counters, a reset,
    # negative values and a reading from the following day.
    for minute, channel, imported, exported in [
        (0, 0, 1000, None), (1, 0, 1100, 40), (2, 0, 1400, 60),
        (3, 1, 5000, 100), (4, 1, 5450, None), (5, 1, None, 145),
    ]:
        add_reading(db, grid, start + timedelta(minutes=minute), 'shelly_rpc_emdata',
                    channel=channel, phase=f'L{channel+1}', imported=imported, exported=exported)
    for minute, imported in [(0, 8000), (1, None), (2, 8500), (3, 100), (4, 150)]:
        add_reading(db, solar, start + timedelta(minutes=minute), 'shelly_rpc_switch', imported=imported)
    add_reading(db, solar, start + timedelta(days=1), 'shelly_rpc_switch', imported=999999)
    db.commit()

    original_rows = db.query(Measurement).filter(
        Measurement.timestamp >= start, Measurement.timestamp < start + timedelta(days=1)
    ).order_by(Measurement.timestamp, Measurement.id).all()
    query_text = []

    def collect_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        query_text.append(statement.lower())

    event.listen(db.bind, 'before_cursor_execute', collect_sql)
    try:
        edges = energy_counter_edges(db, start, start + timedelta(days=1))
    finally:
        event.remove(db.bind, 'before_cursor_execute', collect_sql)

    # Only small, targeted projections; no full Measurement or raw JSON loads.
    assert all('raw_json' not in sql for sql in query_text)
    assert len(edges) < len(original_rows) * 2  # bounded by counter endpoints per key
    for attr in ('energy_import_wh', 'energy_export_wh'):
        assert delta_energy(edges, attr, None) == delta_energy(original_rows, attr, None)
    assert delta_energy(edges, 'energy_import_wh', {'shelly_rpc_emdata'}) == 850
    assert delta_energy(edges, 'energy_export_wh', {'shelly_rpc_emdata'}) == 65
    assert delta_energy(edges, 'energy_import_wh', {'shelly_rpc_switch'}) == 0  # reset: preserve v0.9.56 logic
    day = calculate_day_summary(db, date(2026, 9, 22))
    assert day.imported_kwh == 0.85
    assert day.exported_kwh == 0.065
    assert day.solar_kwh == 0


def test_day_edges_handle_null_source_keys_and_missing_energy(db):
    device = Device(name='Solar', host='192.0.2.8')
    db.add(device)
    db.flush()
    day = datetime(2026, 9, 22, tzinfo=timezone.utc)
    add_reading(db, device, day, 'shelly_rpc_pm', imported=None)
    add_reading(db, device, day + timedelta(seconds=5), 'shelly_rpc_pm', imported=500)
    add_reading(db, device, day + timedelta(seconds=10), 'shelly_rpc_pm', imported=690)
    db.commit()
    rows = energy_counter_edges(db, day, day + timedelta(days=1), {'shelly_rpc_pm'})
    assert delta_energy(rows, 'energy_import_wh') == 190
    assert delta_energy(rows, 'energy_export_wh') is None
    assert energy_counter_edges(db, day, day + timedelta(days=1), {'shelly_rpc_emdata'}) == []


def test_completed_days_are_written_once_and_never_recomputed(db, monkeypatch):
    from app import energy_retention

    grid = Device(name='Grid', host='192.0.2.1')
    db.add(grid)
    db.flush()
    now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    add_reading(db, grid, now - timedelta(days=2), 'shelly_rpc_emdata', imported=1000)
    add_reading(db, grid, now - timedelta(days=2, minutes=-1), 'shelly_rpc_emdata', imported=1200)
    add_reading(db, grid, now - timedelta(days=1), 'shelly_rpc_emdata', imported=2000)
    add_reading(db, grid, now - timedelta(days=1, minutes=-1), 'shelly_rpc_emdata', imported=2400)
    db.add(DailyEnergySummary(date=date(2026, 9, 20), imported_kwh=42, exported_kwh=0, solar_kwh=0))
    db.commit()

    calls = []
    def fake_upsert(session, day):
        calls.append(day)
        computed = calculate_day_summary(session, day)
        session.add(computed)
        session.flush()
        return computed

    monkeypatch.setattr(energy_retention, 'upsert_day_summary', fake_upsert)
    assert ensure_completed_daily_summaries(db, now) == 1
    assert calls == [date(2026, 9, 21)]
    assert db.query(DailyEnergySummary).filter_by(date=date(2026, 9, 20)).one().imported_kwh == 42
    assert db.query(DailyEnergySummary).filter_by(date=date(2026, 9, 21)).one().imported_kwh == 0.4

    # Even if retained raw rows change later, closed days are immutable.
    add_reading(db, grid, now - timedelta(days=1, minutes=-2), 'shelly_rpc_emdata', imported=8000)
    db.commit()
    assert ensure_completed_daily_summaries(db, now) == 0
    assert calls == [date(2026, 9, 21)]
    assert db.query(DailyEnergySummary).filter_by(date=date(2026, 9, 21)).one().imported_kwh == 0.4
    # Raw retention must also skip already completed summaries.
    cleanup_old_raw_measurements(db, 7, now + timedelta(days=31))
    assert calls == [date(2026, 9, 21)]
    assert db.query(DailyEnergySummary).count() == 2
