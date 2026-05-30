from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import DailyEnergySummary, Measurement, utcnow

GRID_ENERGY_SOURCES = {'shelly_3em_gen1_emeter', 'shelly_rpc_emdata'}
SOLAR_ENERGY_SOURCES = {'shelly_rpc_switch', 'shelly_rpc_pm'}


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def delta_energy(rows: list[Measurement], attr: str, source_types: set[str] | None = None) -> float | None:
    first_by_key: dict[tuple[int, str, int | None, str | None], float] = {}
    last_by_key: dict[tuple[int, str, int | None, str | None], float] = {}
    for row in rows:
        if source_types is not None and row.source_type not in source_types:
            continue
        value = getattr(row, attr)
        if value is None:
            continue
        key = (row.device_id, row.source_type, row.channel, row.phase)
        first_by_key.setdefault(key, value)
        last_by_key[key] = value
    if not last_by_key:
        return None
    return sum(max(0.0, last_by_key[k] - first_by_key.get(k, last_by_key[k])) for k in last_by_key)


def calculate_day_summary(db: Session, day: date) -> DailyEnergySummary:
    start, end = day_bounds(day)
    rows = (
        db.query(Measurement)
        .filter(Measurement.timestamp >= start, Measurement.timestamp < end)
        .order_by(Measurement.timestamp.asc())
        .all()
    )
    imported_wh = delta_energy(rows, 'energy_import_wh', GRID_ENERGY_SOURCES) or 0.0
    exported_wh = delta_energy(rows, 'energy_export_wh', GRID_ENERGY_SOURCES) or 0.0
    solar_wh = delta_energy(rows, 'energy_import_wh', SOLAR_ENERGY_SOURCES) or 0.0
    return DailyEnergySummary(
        date=day,
        imported_kwh=imported_wh / 1000.0,
        exported_kwh=exported_wh / 1000.0,
        solar_kwh=solar_wh / 1000.0,
        updated_at=utcnow(),
    )


def upsert_day_summary(db: Session, day: date) -> DailyEnergySummary:
    summary = calculate_day_summary(db, day)
    stmt = pg_insert(DailyEnergySummary).values(
        date=summary.date,
        imported_kwh=summary.imported_kwh,
        exported_kwh=summary.exported_kwh,
        solar_kwh=summary.solar_kwh,
        created_at=utcnow(),
        updated_at=utcnow(),
    ).on_conflict_do_update(
        index_elements=[DailyEnergySummary.date],
        set_={
            'imported_kwh': summary.imported_kwh,
            'exported_kwh': summary.exported_kwh,
            'solar_kwh': summary.solar_kwh,
            'updated_at': utcnow(),
        },
    )
    db.execute(stmt)
    db.flush()
    return db.query(DailyEnergySummary).filter(DailyEnergySummary.date == day).one()


def raw_measurement_days(db: Session, before_day: date) -> list[date]:
    # PostgreSQL date() over timestamptz returns date in the session time zone. The
    # container and DB run UTC by default; if a deployment changes the DB time zone,
    # this still only affects day boundaries, not the retained totals.
    rows = db.execute(
        select(func.date(Measurement.timestamp))
        .where(Measurement.timestamp < datetime.combine(before_day, time.min, tzinfo=timezone.utc))
        .group_by(func.date(Measurement.timestamp))
        .order_by(func.date(Measurement.timestamp))
    ).all()
    return [row[0] for row in rows]


def ensure_completed_daily_summaries(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    count = 0
    for day in raw_measurement_days(db, before_day=today):
        upsert_day_summary(db, day)
        count += 1
    if count:
        db.commit()
    return count


def cleanup_old_raw_measurements(db: Session, raw_retention_days: int, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    raw_retention_days = max(7, min(3650, int(raw_retention_days or 30)))
    cutoff_day = (now - timedelta(days=raw_retention_days)).date()
    cutoff = datetime.combine(cutoff_day, time.min, tzinfo=timezone.utc)

    # First materialize all complete days that will be deleted, then remove only raw rows.
    deleted_candidate_days = raw_measurement_days(db, before_day=cutoff_day)
    for day in deleted_candidate_days:
        upsert_day_summary(db, day)

    result = db.execute(delete(Measurement).where(Measurement.timestamp < cutoff))
    db.commit()
    return int(result.rowcount or 0)


def get_stored_total_kwh(db: Session, today_values: tuple[float | None, float | None, float | None]) -> tuple[float | None, float | None, float | None]:
    today_imported, today_exported, today_solar = today_values
    imported_sum, exported_sum, solar_sum = db.query(
        func.coalesce(func.sum(DailyEnergySummary.imported_kwh), 0.0),
        func.coalesce(func.sum(DailyEnergySummary.exported_kwh), 0.0),
        func.coalesce(func.sum(DailyEnergySummary.solar_kwh), 0.0),
    ).one()

    imported_total = float(imported_sum) + (today_imported or 0.0)
    exported_total = float(exported_sum) + (today_exported or 0.0)
    solar_total = float(solar_sum) + (today_solar or 0.0)
    return imported_total, exported_total, solar_total
