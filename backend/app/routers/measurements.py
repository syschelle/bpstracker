from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device, DeviceStatus, Measurement, User
from ..energy_retention import (
    GRID_ENERGY_SOURCES,
    SOLAR_ENERGY_SOURCES,
    delta_energy,
    ensure_completed_daily_summaries,
    get_stored_total_kwh,
)
from ..routers.settings import get_finance_settings_from_db, get_retention_settings_from_db, get_simulation_settings_from_db, get_ui_settings_from_db
from ..schemas import HistoryPoint, MeasurementRead, SummaryResponse
from ..simulation import simulated_history, simulated_latest, simulated_summary
from ..security import get_current_user

router = APIRouter(prefix='/api/measurements', tags=['measurements'])

GRID_POWER_SOURCES = {'shelly_3em_gen1_total', 'shelly_rpc_em_total'}


def _avg(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _bucket_seconds(start: datetime, end: datetime) -> int:
    """Pick a display-friendly bucket size for the selected history range.

    Returning raw rows creates a visually broken chart because a Shelly 3EM stores
    one row per phase and a Shelly 2PM can store multiple channels at nearly the
    same timestamp. Recharts then connects different channels vertically. The
    history chart should therefore receive one aggregated value per time bucket.
    """
    hours = max(0.0, (end - start).total_seconds() / 3600)
    if hours <= 24:
        return 60          # 1-minute buckets, max ~1440 points
    if hours <= 24 * 7:
        return 15 * 60     # 15-minute buckets, max ~672 points
    return 60 * 60         # 1-hour buckets, max ~720 points for 30 days


def _floor_to_bucket(ts: datetime, bucket_seconds: int) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % bucket_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _raw_history_rows(
    db: Session,
    start: datetime,
    end: datetime,
    device_id: int | None = None,
    source_type: str | None = None,
    limit: int = 20000,
) -> list[Measurement]:
    query = db.query(Measurement).filter(Measurement.timestamp >= start, Measurement.timestamp <= end)
    if device_id:
        query = query.filter(Measurement.device_id == device_id)
    if source_type:
        query = query.filter(Measurement.source_type == source_type)
    return query.order_by(Measurement.timestamp.asc()).limit(limit).all()


@router.get('/latest', response_model=list[MeasurementRead])
def latest_measurements(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Measurement | MeasurementRead]:
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        ui = get_ui_settings_from_db(db)
        return simulated_latest(ui.timezone)

    subq = (
        db.query(Measurement.device_id, Measurement.source_type, Measurement.channel, Measurement.phase, func.max(Measurement.timestamp).label('max_ts'))
        .group_by(Measurement.device_id, Measurement.source_type, Measurement.channel, Measurement.phase)
        .subquery()
    )
    rows = (
        db.query(Measurement)
        .join(
            subq,
            (Measurement.device_id == subq.c.device_id)
            & (Measurement.source_type == subq.c.source_type)
            & (Measurement.timestamp == subq.c.max_ts)
            & (Measurement.channel.is_not_distinct_from(subq.c.channel))
            & (Measurement.phase.is_not_distinct_from(subq.c.phase)),
        )
        .order_by(Measurement.device_id, Measurement.source_type, Measurement.channel, Measurement.phase)
        .all()
    )
    return rows


@router.get('/history', response_model=list[HistoryPoint])
def history(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    device_id: int | None = None,
    source_type: str | None = None,
    limit: int = Query(default=20000, ge=1, le=50000),
) -> list[HistoryPoint]:
    """Return chart-ready aggregated history points.

    The database intentionally stores normalized raw measurements. For devices
    such as Shelly 3EM this means several rows per polling timestamp, e.g. L1,
    L2, L3 and one total row. Plotting those rows as one line creates the
    vertical spikes seen in the history view. This endpoint now aggregates rows
    into time buckets and returns one value per bucket.
    """
    end = end or datetime.now(timezone.utc)
    start = start or (end - timedelta(hours=24))
    bucket_seconds = _bucket_seconds(start, end)
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        ui = get_ui_settings_from_db(db)
        return simulated_history(start, end, ui.timezone, bucket_seconds)

    rows = _raw_history_rows(db, start, end, device_id=device_id, source_type=source_type, limit=limit)

    buckets: dict[datetime, dict] = defaultdict(lambda: {
        'solar_by_key': defaultdict(list),
        'grid_values': [],
        'fallback_by_key': defaultdict(list),
    })

    for row in rows:
        bucket = _floor_to_bucket(row.timestamp, bucket_seconds)
        value = row.power_w if row.power_w is not None else row.total_power_w
        if value is None:
            continue

        key = (row.device_id, row.source_type, row.channel, row.phase)
        if row.source_type in SOLAR_ENERGY_SOURCES and row.power_w is not None:
            # Average per channel within a bucket, then sum channels. This avoids
            # alternating 0/actual values when a Shelly 2PM has multiple channels.
            buckets[bucket]['solar_by_key'][key].append(max(0.0, row.power_w))
        elif row.source_type in GRID_POWER_SOURCES:
            buckets[bucket]['grid_values'].append(row.total_power_w if row.total_power_w is not None else value)
        else:
            buckets[bucket]['fallback_by_key'][key].append(value)

    points: list[HistoryPoint] = []
    for bucket in sorted(buckets):
        data = buckets[bucket]
        solar_parts = [_avg(values) for values in data['solar_by_key'].values()]
        solar_power = sum(value for value in solar_parts if value is not None) if solar_parts else None
        grid_power = _avg(data['grid_values']) if data['grid_values'] else None
        fallback_parts = [_avg(values) for values in data['fallback_by_key'].values()]
        fallback_power = sum(value for value in fallback_parts if value is not None) if fallback_parts else None

        # Keep the existing frontend compatible: it plots power_w first, then
        # total_power_w. Prefer solar when available; otherwise grid total; then
        # a generic fallback for older/unclassified source types.
        display_power = solar_power if solar_power is not None else (grid_power if grid_power is not None else fallback_power)
        if display_power is None:
            continue
        points.append(HistoryPoint(
            timestamp=bucket,
            device_id=0,
            source_type='aggregate_power',
            power_w=display_power,
            total_power_w=grid_power,
            solar_power_w=solar_power,
            grid_power_w=grid_power,
        ))

    return points


@router.get('/summary', response_model=SummaryResponse)
def summary(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SummaryResponse:
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        finance = get_finance_settings_from_db(db)
        ui = get_ui_settings_from_db(db)
        retention = get_retention_settings_from_db(db)
        simulated = simulated_summary(
            ui.timezone,
            kwh_price=finance.kwh_price_eur,
            investment=finance.investment_cost_eur,
            currency_code=finance.currency_code,
        )
        simulated.raw_retention_days = retention.raw_retention_days
        return simulated

    latest = latest_measurements(_, db)
    device_count = db.query(Device).count()
    online_count = db.query(DeviceStatus).filter(DeviceStatus.online.is_(True)).count()
    current_total_power = None
    current_grid_power = None
    current_solar_power = None
    last_at = None

    for row in latest:
        if last_at is None or row.timestamp > last_at:
            last_at = row.timestamp
        if row.source_type in GRID_POWER_SOURCES and row.total_power_w is not None:
            current_total_power = row.total_power_w
            current_grid_power = row.total_power_w
        if row.source_type in SOLAR_ENERGY_SOURCES and row.power_w is not None:
            # Assumption: switch/PM channel is the solar feed-in point.
            current_solar_power = (current_solar_power or 0.0) + max(0.0, row.power_w)

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Keep completed days materialized before totals are calculated. Raw rows may
    # later be deleted by the retention job, but these daily summaries stay forever.
    ensure_completed_daily_summaries(db, now)

    today_rows = db.query(Measurement).filter(Measurement.timestamp >= today).order_by(Measurement.timestamp.asc()).all()

    imported_today_wh = delta_energy(today_rows, 'energy_import_wh', GRID_ENERGY_SOURCES)
    exported_today_wh = delta_energy(today_rows, 'energy_export_wh', GRID_ENERGY_SOURCES)
    solar_today_wh = delta_energy(today_rows, 'energy_import_wh', SOLAR_ENERGY_SOURCES)

    imported_today_kwh = imported_today_wh / 1000 if imported_today_wh is not None else None
    exported_today_kwh = exported_today_wh / 1000 if exported_today_wh is not None else None
    solar_today_kwh = solar_today_wh / 1000 if solar_today_wh is not None else None
    imported_total_kwh, exported_total_kwh, solar_total_kwh = get_stored_total_kwh(
        db,
        (imported_today_kwh, exported_today_kwh, solar_today_kwh),
    )

    finance = get_finance_settings_from_db(db)
    retention = get_retention_settings_from_db(db)
    price = finance.kwh_price_eur
    investment = finance.investment_cost_eur

    consumption_cost_today = imported_today_kwh * price if imported_today_kwh is not None else None
    savings_today = solar_today_kwh * price if solar_today_kwh is not None else None
    savings_total = solar_total_kwh * price if solar_total_kwh is not None else None

    remaining = None
    progress = None
    estimated_days = None
    estimated_date = None
    if investment > 0 and savings_total is not None:
        remaining = max(0.0, investment - savings_total)
        progress = min(100.0, max(0.0, (savings_total / investment) * 100.0))
        if remaining > 0 and savings_today and savings_today > 0:
            estimated_days = remaining / savings_today
            estimated_date = now + timedelta(days=estimated_days)
        elif remaining == 0:
            estimated_days = 0.0
            estimated_date = now

    return SummaryResponse(
        current_grid_power_w=current_grid_power,
        current_solar_power_w=current_solar_power,
        current_total_power_w=current_total_power,
        imported_today_kwh=imported_today_kwh,
        exported_today_kwh=exported_today_kwh,
        solar_today_kwh=solar_today_kwh,
        imported_total_kwh=imported_total_kwh,
        exported_total_kwh=exported_total_kwh,
        solar_total_kwh=solar_total_kwh,
        kwh_price_eur=price,
        investment_cost_eur=investment,
        currency_code=finance.currency_code,
        consumption_cost_today_eur=consumption_cost_today,
        savings_today_eur=savings_today,
        savings_total_eur=savings_total,
        remaining_to_breakeven_eur=remaining,
        breakeven_progress_percent=progress,
        estimated_breakeven_days=estimated_days,
        estimated_breakeven_date=estimated_date,
        last_measurement_at=last_at,
        device_count=device_count,
        online_device_count=online_count,
        raw_retention_days=retention.raw_retention_days,
    )



@router.get('/export.csv')
def export_csv(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
) -> Response:
    end = end or datetime.now(timezone.utc)
    start = start or (end - timedelta(hours=24))
    rows = _raw_history_rows(db, start=start, end=end, limit=50000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['timestamp', 'device_id', 'source_type', 'channel', 'phase', 'power_w', 'voltage_v', 'current_a', 'power_factor', 'energy_import_wh', 'energy_export_wh', 'total_power_w'])
    for row in rows:
        writer.writerow([row.timestamp.isoformat(), row.device_id, row.source_type, row.channel, row.phase, row.power_w, row.voltage_v, row.current_a, row.power_factor, row.energy_import_wh, row.energy_export_wh, row.total_power_w])
    return Response(content=output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="bpstracker-measurements.csv"'})
