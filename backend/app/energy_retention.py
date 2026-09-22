from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import DailyEnergySummary, Measurement, utcnow

GRID_ENERGY_SOURCES = {'shelly_3em_gen1_emeter', 'shelly_rpc_emdata'}
SOLAR_ENERGY_SOURCES = {'shelly_rpc_switch', 'shelly_rpc_pm'}


@dataclass(frozen=True, slots=True)
class EnergyCounterRow:
    """Only the columns needed for the existing energy-delta calculation.

    Avoid loading full Measurement ORM objects (in particular raw_json) for
    every poll accumulated throughout the day. The counter values and grouping
    keys are deliberately identical to those used by delta_energy().
    """

    device_id: int
    source_type: str
    channel: int | None
    phase: str | None
    energy_import_wh: float | None = None
    energy_export_wh: float | None = None


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def delta_energy(rows: list[Measurement] | list[EnergyCounterRow], attr: str, source_types: set[str] | None = None) -> float | None:
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


def energy_counter_edges(
    db: Session,
    start: datetime,
    end: datetime,
    source_types: set[str] | None = None,
) -> list[EnergyCounterRow]:
    """Load only the first/last *non-null* counters for each measurement key.

    An indexed lookup per key/counter avoids materializing the entire day's
    readings (and their often large raw JSON payloads) on every dashboard or
    Kindle refresh. Keep first and last for import and export independent: some
    Shelly records contain only one of the two counters. Existing reset and
    classification rules remain in delta_energy() and the calling routers.
    """
    key_columns = (
        Measurement.device_id,
        Measurement.source_type,
        Measurement.channel,
        Measurement.phase,
    )
    keys_query = (
        db.query(*key_columns)
        .filter(Measurement.timestamp >= start, Measurement.timestamp < end)
        .filter(
            (Measurement.energy_import_wh.isnot(None))
            | (Measurement.energy_export_wh.isnot(None))
        )
    )
    if source_types is not None:
        keys_query = keys_query.filter(Measurement.source_type.in_(source_types))

    rows: list[EnergyCounterRow] = []
    for device_id, source_type, channel, phase in keys_query.distinct().all():
        key_filters = (
            Measurement.device_id == device_id,
            Measurement.source_type == source_type,
            Measurement.channel == channel if channel is not None else Measurement.channel.is_(None),
            Measurement.phase == phase if phase is not None else Measurement.phase.is_(None),
            Measurement.timestamp >= start,
            Measurement.timestamp < end,
        )
        for attr in ('energy_import_wh', 'energy_export_wh'):
            column = getattr(Measurement, attr)
            base = db.query(column).filter(*key_filters, column.isnot(None))
            first = base.order_by(Measurement.timestamp.asc(), Measurement.id.asc()).first()
            if first is None:
                continue
            last = base.order_by(Measurement.timestamp.desc(), Measurement.id.desc()).first()
            values = {'device_id': device_id, 'source_type': source_type, 'channel': channel, 'phase': phase}
            rows.append(EnergyCounterRow(**values, **{attr: first[0]}))
            rows.append(EnergyCounterRow(**values, **{attr: last[0]}))
    return rows


def calculate_day_summary(db: Session, day: date) -> DailyEnergySummary:
    start, end = day_bounds(day)
    rows = energy_counter_edges(db, start, end, GRID_ENERGY_SOURCES | SOLAR_ENERGY_SOURCES)
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
    # SQLite returns the result of date() as text in unit tests; PostgreSQL
    # returns a date. Normalize both without changing the production query.
    return [date.fromisoformat(row[0]) if isinstance(row[0], str) else row[0] for row in rows]


def ensure_completed_daily_summaries(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    # Completed days are immutable. Only repair missing days (e.g. after an
    # outage); never overwrite a previously stored daily total automatically.
    stored_days = set(db.scalars(select(DailyEnergySummary.date).where(DailyEnergySummary.date < today)).all())
    count = 0
    for day in raw_measurement_days(db, before_day=today):
        if day in stored_days:
            continue
        upsert_day_summary(db, day)
        count += 1
    if count:
        db.commit()
    return count


def cleanup_old_raw_measurements(
    db: Session,
    raw_retention_days: int,
    now: datetime | None = None,
    *,
    raw_retention_hours: int | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)

    if raw_retention_hours is not None and raw_retention_hours > 0:
        retention_hours = max(1, min(3650 * 24, int(raw_retention_hours)))
        cutoff = now - timedelta(hours=retention_hours)
        cutoff_day = cutoff.date()

        # Hour-based cleanup is used by very small devices such as the Raspberry Pi
        # Zero 2 W. Before deleting any rows from a completed day, materialize that
        # whole day into DailyEnergySummary so total balance and total cost cards stay
        # available even when raw measurements are kept for only 24 hours.
        summarize_before_day = min(now.date(), cutoff_day + timedelta(days=1))
        deleted_candidate_days = raw_measurement_days(db, before_day=summarize_before_day)
    else:
        raw_retention_days = max(7, min(3650, int(raw_retention_days or 30)))
        cutoff_day = (now - timedelta(days=raw_retention_days)).date()
        cutoff = datetime.combine(cutoff_day, time.min, tzinfo=timezone.utc)

        # First materialize all complete days that will be deleted, then remove only raw rows.
        deleted_candidate_days = raw_measurement_days(db, before_day=cutoff_day)

    if deleted_candidate_days:
        stored_days = set(db.scalars(
            select(DailyEnergySummary.date).where(DailyEnergySummary.date.in_(deleted_candidate_days))
        ).all())
        for day in deleted_candidate_days:
            if day not in stored_days:
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
