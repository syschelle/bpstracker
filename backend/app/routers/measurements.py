from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Device, DeviceStatus, Measurement, User
from ..energy_retention import (
    GRID_ENERGY_SOURCES,
    SOLAR_ENERGY_SOURCES,
    delta_energy,
    get_stored_total_kwh,
)
from ..routers.settings import get_finance_settings_from_db, get_live_data_max_hours, get_public_dashboard_settings_from_db, get_retention_settings_from_db, get_simulation_settings_from_db, get_ui_settings_from_db
from ..schemas import HistoryPoint, HistorySeriesResponse, HistoryTotalsResponse, MeasurementRead, SummaryResponse
from ..simulation import simulated_history, simulated_latest, simulated_summary
from ..security import get_current_user

router = APIRouter(prefix='/api/measurements', tags=['measurements'])

HISTORY_ROW_LIMIT_DEFAULT = 500000
HISTORY_ROW_LIMIT_MAX = 500000


@dataclass(slots=True)
class HistoryMeasurementRow:
    id: int
    timestamp: datetime
    device_id: int
    source_type: str
    channel: int | None = None
    phase: str | None = None
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    power_factor: float | None = None
    energy_import_wh: float | None = None
    energy_export_wh: float | None = None
    total_power_w: float | None = None


def _clamp_live_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    max_hours = get_live_data_max_hours()
    if max_hours is None:
        return start, end
    earliest = end - timedelta(hours=max_hours)
    if start < earliest:
        start = earliest
    return start, end


def _require_public_dashboard(db: Session) -> None:
    if not get_public_dashboard_settings_from_db(db).enabled:
        raise HTTPException(status_code=404, detail='Public dashboard is disabled')

GRID_POWER_SOURCES = {'shelly_3em_gen1_total', 'shelly_rpc_em_total'}

DEVICE_PURPOSE_AUTO = 'auto'
DEVICE_PURPOSE_GRID = 'grid'
DEVICE_PURPOSE_SOLAR = 'solar'
DEVICE_PURPOSE_CONSUMER = 'consumer'
DEVICE_PURPOSE_IGNORED = 'ignored'


def _device_purposes(db: Session) -> dict[int, str]:
    rows = db.query(Device.id, Device.purpose).all()
    return {int(device_id): str(purpose or DEVICE_PURPOSE_AUTO) for device_id, purpose in rows}


def _device_configs(db: Session) -> dict[int, tuple[str, int | None]]:
    rows = db.query(Device.id, Device.device_type, Device.channel).all()
    configs: dict[int, tuple[str, int | None]] = {}
    for device_id, device_type, channel in rows:
        type_value = getattr(device_type, 'value', device_type)
        configs[int(device_id)] = (str(type_value), channel)
    return configs


def _measurement_matches_device_config(row: Measurement | MeasurementRead | HistoryMeasurementRow, configs: dict[int, tuple[str, int | None]]) -> bool:
    config = configs.get(int(row.device_id))
    if config is None:
        return True
    device_type, configured_channel = config
    if configured_channel is None:
        return True
    # Shelly 3EM Gen1 exposes L1/L2/L3 as channels 0/1/2 and exposes a separate
    # device-wide total row without a channel. When a phase/channel is configured
    # explicitly in setup, dashboard/latest/summary views must not show or count
    # the unconfigured total row.
    if device_type == 'shelly_3em_gen1' and row.source_type == 'shelly_3em_gen1_total':
        return False
    return row.channel == configured_channel


def _purpose_for(row: Measurement | MeasurementRead | HistoryMeasurementRow, purposes: dict[int, str]) -> str:
    return purposes.get(int(row.device_id), DEVICE_PURPOSE_AUTO)


def _is_solar_row(row: Measurement | MeasurementRead | HistoryMeasurementRow, purposes: dict[int, str]) -> bool:
    purpose = _purpose_for(row, purposes)
    if purpose == DEVICE_PURPOSE_IGNORED:
        return False
    if purpose == DEVICE_PURPOSE_SOLAR:
        return True
    return purpose == DEVICE_PURPOSE_AUTO and row.source_type in SOLAR_ENERGY_SOURCES


def _is_grid_row(row: Measurement | MeasurementRead | HistoryMeasurementRow, purposes: dict[int, str]) -> bool:
    purpose = _purpose_for(row, purposes)
    if purpose == DEVICE_PURPOSE_IGNORED:
        return False
    if purpose == DEVICE_PURPOSE_GRID:
        return True
    return purpose == DEVICE_PURPOSE_AUTO and row.source_type in (GRID_POWER_SOURCES | GRID_ENERGY_SOURCES)


def _solar_power_value(row: Measurement | MeasurementRead | HistoryMeasurementRow) -> float | None:
    value = row.power_w if row.power_w is not None else row.total_power_w
    return abs(value) if value is not None else None


def _grid_power_value(row: Measurement | MeasurementRead | HistoryMeasurementRow) -> float | None:
    if row.total_power_w is not None:
        return row.total_power_w
    return row.power_w

DEFAULT_BATTERY_ROUNDTRIP_EFFICIENCY = 0.85


def battery_analysis(
    exported_today_kwh: float | None,
    exported_total_kwh: float | None,
    *,
    kwh_price: float,
    battery_cost: float,
    battery_capacity_kwh: float,
    battery_roundtrip_efficiency: float,
    remaining_bps_investment: float | None,
) -> dict[str, float | bool | None]:
    """Estimate battery payback while respecting open BPS amortization.

    Feed-in is treated as unpaid. The standalone battery payback shows how long
    the battery itself would take based on otherwise exported surplus. The
    combined payback additionally includes the remaining open amortization of
    the balcony PV system. This avoids presenting a battery as "worthwhile" while
    the existing installation has not yet paid for itself.
    """
    empty = {
        'battery_remaining_bps_investment_eur': max(0.0, remaining_bps_investment or 0.0),
        'battery_combined_investment_eur': None,
        'battery_combined_payback_days': None,
        'battery_combined_payback_years': None,
        'battery_usable_surplus_today_kwh': None,
        'battery_savings_today_eur': None,
        'battery_savings_total_potential_eur': None,
        'battery_payback_days': None,
        'battery_payback_years': None,
        'battery_worthwhile': None,
    }
    efficiency = min(1.0, max(0.5, battery_roundtrip_efficiency or DEFAULT_BATTERY_ROUNDTRIP_EFFICIENCY))
    if battery_cost <= 0 or battery_capacity_kwh <= 0 or kwh_price <= 0:
        return empty

    remaining_bps = max(0.0, remaining_bps_investment or 0.0)
    export_today = max(0.0, exported_today_kwh or 0.0)
    export_total = max(0.0, exported_total_kwh or 0.0)
    usable_today = min(export_today, max(0.0, battery_capacity_kwh))
    daily_battery_savings = usable_today * efficiency * kwh_price
    total_potential = export_total * efficiency * kwh_price

    battery_payback_days = battery_cost / daily_battery_savings if daily_battery_savings > 0 else None
    battery_payback_years = battery_payback_days / 365.25 if battery_payback_days is not None else None

    combined_investment = remaining_bps + battery_cost
    combined_payback_days = combined_investment / daily_battery_savings if daily_battery_savings > 0 else None
    combined_payback_years = combined_payback_days / 365.25 if combined_payback_days is not None else None

    # "Worthwhile" now includes the still-open BPS amortization, if any.
    worthwhile = bool(combined_payback_days is not None and combined_payback_days <= 365.25 * 10)

    return {
        'battery_remaining_bps_investment_eur': remaining_bps,
        'battery_combined_investment_eur': combined_investment,
        'battery_combined_payback_days': combined_payback_days,
        'battery_combined_payback_years': combined_payback_years,
        'battery_usable_surplus_today_kwh': usable_today,
        'battery_savings_today_eur': daily_battery_savings,
        'battery_savings_total_potential_eur': total_potential,
        'battery_payback_days': battery_payback_days,
        'battery_payback_years': battery_payback_years,
        'battery_worthwhile': worthwhile,
    }



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

    On Raspberry Pi Zero 2 W deployments the 24h view intentionally uses 5-minute
    buckets. This reduces the JSON payload from up to 1440 chart points to about
    288 points and noticeably lowers browser/rendering work on low-resource
    systems while still preserving the 24h trend.
    """
    hours = max(0.0, (end - start).total_seconds() / 3600)
    if hours <= 24:
        if get_settings().pi_zero_2w_mode:
            return 5 * 60  # 5-minute buckets, max ~288 points on Pi Zero 2 W
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
    limit: int = HISTORY_ROW_LIMIT_DEFAULT,
) -> list[HistoryMeasurementRow]:
    query = (
        db.query(
            Measurement.id,
            Measurement.timestamp,
            Measurement.device_id,
            Measurement.source_type,
            Measurement.channel,
            Measurement.phase,
            Measurement.power_w,
            Measurement.voltage_v,
            Measurement.current_a,
            Measurement.power_factor,
            Measurement.energy_import_wh,
            Measurement.energy_export_wh,
            Measurement.total_power_w,
        )
        .filter(Measurement.timestamp >= start, Measurement.timestamp <= end)
        .filter(or_(
            Measurement.power_w.is_not(None),
            Measurement.total_power_w.is_not(None),
            Measurement.energy_import_wh.is_not(None),
            Measurement.energy_export_wh.is_not(None),
        ))
    )
    if device_id:
        query = query.filter(Measurement.device_id == device_id)
    if source_type:
        query = query.filter(Measurement.source_type == source_type)

    # History does not need raw_json and does not render voltage-only rows.
    # Selecting only the columns needed for chart aggregation avoids loading large
    # JSON payloads into Python, which was the main bottleneck on Raspberry Pi
    # Zero 2 W systems. Read newest rows first to keep recent data when the safety
    # limit is reached, then sort back ascending for chart rendering.
    rows = query.order_by(Measurement.timestamp.desc()).limit(limit).all()
    lightweight_rows = [HistoryMeasurementRow(*row) for row in rows]
    return sorted(lightweight_rows, key=lambda row: row.timestamp)


@router.get('/latest', response_model=list[MeasurementRead])
def latest_measurements(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Measurement | MeasurementRead]:
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        ui = get_ui_settings_from_db(db)
        devices = db.query(Device).order_by(Device.id).all()
        return simulated_latest(ui.timezone, devices, simulation.pv_peak_w, simulation.baseload_day_w, simulation.baseload_night_w)

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
    configs = _device_configs(db)
    return [row for row in rows if _measurement_matches_device_config(row, configs)]



def _integrated_kwh_from_history(points: list[HistoryPoint], selector) -> float | None:
    if not points:
        return None
    sorted_points = sorted(points, key=lambda point: point.timestamp)
    intervals: list[float] = []
    for index, point in enumerate(sorted_points):
        if index < len(sorted_points) - 1:
            seconds = (sorted_points[index + 1].timestamp - point.timestamp).total_seconds()
        elif intervals:
            seconds = intervals[-1]
        else:
            seconds = 0.0
        intervals.append(max(0.0, seconds))

    total_wh = 0.0
    used = False
    for point, seconds in zip(sorted_points, intervals):
        value = selector(point)
        if value is None or seconds <= 0:
            continue
        total_wh += value * (seconds / 3600.0)
        used = True
    return total_wh / 1000.0 if used else None


def _history_power_totals(points: list[HistoryPoint]) -> HistoryTotalsResponse:
    return HistoryTotalsResponse(
        imported_kwh=_integrated_kwh_from_history(
            points,
            lambda point: max(0.0, point.grid_power_w) if point.grid_power_w is not None else None,
        ),
        exported_kwh=_integrated_kwh_from_history(
            points,
            lambda point: abs(min(0.0, point.grid_power_w)) if point.grid_power_w is not None else None,
        ),
        solar_kwh=_integrated_kwh_from_history(
            points,
            lambda point: abs(point.solar_power_w) if point.solar_power_w is not None else None,
        ),
    )


def _history_points_from_rows(
    rows: list[HistoryMeasurementRow],
    purposes: dict[int, str],
    configs: dict[int, tuple[str, int | None]],
    bucket_seconds: int,
) -> list[HistoryPoint]:
    buckets: dict[datetime, dict] = defaultdict(lambda: {
        'solar_by_key': defaultdict(list),
        'grid_values': [],
        'fallback_by_key': defaultdict(list),
    })

    for row in rows:
        if not _measurement_matches_device_config(row, configs):
            continue
        bucket = _floor_to_bucket(row.timestamp, bucket_seconds)
        value = row.power_w if row.power_w is not None else row.total_power_w
        if value is None:
            continue

        key = (row.device_id, row.source_type, row.channel, row.phase)
        if _is_solar_row(row, purposes):
            # Average per channel within a bucket, then sum channels. This avoids
            # alternating 0/actual values when a Shelly 2PM has multiple channels.
            solar_value = _solar_power_value(row)
            if solar_value is not None:
                buckets[bucket]['solar_by_key'][key].append(solar_value)
        elif _is_grid_row(row, purposes):
            grid_value = _grid_power_value(row)
            if grid_value is not None:
                buckets[bucket]['grid_values'].append(grid_value)
        elif _purpose_for(row, purposes) != DEVICE_PURPOSE_IGNORED:
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


def _history_totals_from_rows(
    rows: list[HistoryMeasurementRow],
    purposes: dict[int, str],
    configs: dict[int, tuple[str, int | None]],
    bucket_seconds: int,
    points: list[HistoryPoint] | None = None,
) -> HistoryTotalsResponse:
    visible_rows = [row for row in rows if _measurement_matches_device_config(row, configs)]
    grid_rows = [row for row in visible_rows if _is_grid_row(row, purposes)]
    solar_rows = [row for row in visible_rows if _is_solar_row(row, purposes)]

    imported_wh = delta_energy(grid_rows, 'energy_import_wh', None)
    exported_wh = delta_energy(grid_rows, 'energy_export_wh', None)
    solar_wh = delta_energy(solar_rows, 'energy_import_wh', None)

    totals = HistoryTotalsResponse(
        imported_kwh=imported_wh / 1000.0 if imported_wh is not None else None,
        exported_kwh=exported_wh / 1000.0 if exported_wh is not None else None,
        solar_kwh=solar_wh / 1000.0 if solar_wh is not None else None,
    )

    if totals.imported_kwh is None or totals.exported_kwh is None or totals.solar_kwh is None:
        fallback_points = points if points is not None else _history_points_from_rows(rows, purposes, configs, bucket_seconds)
        fallback = _history_power_totals(fallback_points)
        if totals.imported_kwh is None:
            totals.imported_kwh = fallback.imported_kwh
        if totals.exported_kwh is None:
            totals.exported_kwh = fallback.exported_kwh
        if totals.solar_kwh is None:
            totals.solar_kwh = fallback.solar_kwh

    return totals


def _history_series_from_rows(
    rows: list[HistoryMeasurementRow],
    purposes: dict[int, str],
    configs: dict[int, tuple[str, int | None]],
    bucket_seconds: int,
) -> HistorySeriesResponse:
    points = _history_points_from_rows(rows, purposes, configs, bucket_seconds)
    totals = _history_totals_from_rows(rows, purposes, configs, bucket_seconds, points)
    return HistorySeriesResponse(points=points, totals=totals)


@router.get('/history/totals', response_model=HistoryTotalsResponse)
def history_totals(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    device_id: int | None = None,
    source_type: str | None = None,
    limit: int = Query(default=HISTORY_ROW_LIMIT_DEFAULT, ge=1, le=HISTORY_ROW_LIMIT_MAX),
) -> HistoryTotalsResponse:
    """Return energy totals for the currently selected history range.

    The chart itself shows aggregated power points. The totals use cumulative
    energy counter deltas where available, matching dashboard/summary semantics.
    For simulations or legacy rows without energy counters, they fall back to
    integrating the charted power values over the selected range.
    """
    end = end or datetime.now(timezone.utc)
    start = start or (end - timedelta(hours=24))
    start, end = _clamp_live_window(start, end)
    bucket_seconds = _bucket_seconds(start, end)
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        ui = get_ui_settings_from_db(db)
        return _history_power_totals(simulated_history(start, end, ui.timezone, bucket_seconds, simulation.pv_peak_w, simulation.baseload_day_w, simulation.baseload_night_w))

    rows = _raw_history_rows(db, start, end, device_id=device_id, source_type=source_type, limit=limit)
    purposes = _device_purposes(db)
    configs = _device_configs(db)
    return _history_totals_from_rows(rows, purposes, configs, bucket_seconds)


@router.get('/history/series', response_model=HistorySeriesResponse)
def history_series(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    device_id: int | None = None,
    source_type: str | None = None,
    limit: int = Query(default=HISTORY_ROW_LIMIT_DEFAULT, ge=1, le=HISTORY_ROW_LIMIT_MAX),
) -> HistorySeriesResponse:
    """Return chart-ready history points and matching totals in one database pass."""
    end = end or datetime.now(timezone.utc)
    start = start or (end - timedelta(hours=24))
    start, end = _clamp_live_window(start, end)
    bucket_seconds = _bucket_seconds(start, end)
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        ui = get_ui_settings_from_db(db)
        points = simulated_history(start, end, ui.timezone, bucket_seconds, simulation.pv_peak_w, simulation.baseload_day_w, simulation.baseload_night_w)
        return HistorySeriesResponse(points=points, totals=_history_power_totals(points))

    rows = _raw_history_rows(db, start, end, device_id=device_id, source_type=source_type, limit=limit)
    purposes = _device_purposes(db)
    configs = _device_configs(db)
    return _history_series_from_rows(rows, purposes, configs, bucket_seconds)


@router.get('/history', response_model=list[HistoryPoint])
def history(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    device_id: int | None = None,
    source_type: str | None = None,
    limit: int = Query(default=HISTORY_ROW_LIMIT_DEFAULT, ge=1, le=HISTORY_ROW_LIMIT_MAX),
) -> list[HistoryPoint]:
    """Return chart-ready aggregated history points.

    The database intentionally stores normalized raw measurements. For devices
    such as Shelly 3EM this means several rows per polling timestamp, e.g. L1,
    L2, L3 and one total row. Plotting those rows as one line creates the
    vertical spikes seen in the history view. This endpoint aggregates rows into
    time buckets and returns one value per bucket.
    """
    end = end or datetime.now(timezone.utc)
    start = start or (end - timedelta(hours=24))
    start, end = _clamp_live_window(start, end)
    bucket_seconds = _bucket_seconds(start, end)
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        ui = get_ui_settings_from_db(db)
        return simulated_history(start, end, ui.timezone, bucket_seconds, simulation.pv_peak_w, simulation.baseload_day_w, simulation.baseload_night_w)

    rows = _raw_history_rows(db, start, end, device_id=device_id, source_type=source_type, limit=limit)
    purposes = _device_purposes(db)
    configs = _device_configs(db)
    return _history_points_from_rows(rows, purposes, configs, bucket_seconds)


@router.get('/summary', response_model=SummaryResponse)
def summary(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SummaryResponse:
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        finance = get_finance_settings_from_db(db)
        ui = get_ui_settings_from_db(db)
        retention = get_retention_settings_from_db(db)
        public_dashboard = get_public_dashboard_settings_from_db(db)
        devices = db.query(Device).order_by(Device.id).all()
        simulated = simulated_summary(
            ui.timezone,
            kwh_price=finance.kwh_price_eur,
            investment=finance.investment_cost_eur,
            currency_code=finance.currency_code,
            devices=devices,
            pv_peak_w=simulation.pv_peak_w,
            day_baseload_w=simulation.baseload_day_w,
            night_baseload_w=simulation.baseload_night_w,
        )
        battery = battery_analysis(
            simulated.exported_today_kwh,
            simulated.exported_total_kwh,
            kwh_price=finance.kwh_price_eur,
            battery_cost=finance.battery_cost_eur if finance.battery_analysis_enabled else 0.0,
            battery_capacity_kwh=finance.battery_capacity_kwh if finance.battery_analysis_enabled else 0.0,
            battery_roundtrip_efficiency=finance.battery_roundtrip_efficiency,
            remaining_bps_investment=simulated.remaining_to_breakeven_eur,
        )
        for key, value in battery.items():
            setattr(simulated, key, value)
        simulated.battery_analysis_enabled = finance.battery_analysis_enabled
        simulated.battery_cost_eur = finance.battery_cost_eur
        simulated.battery_capacity_kwh = finance.battery_capacity_kwh
        simulated.battery_roundtrip_efficiency = finance.battery_roundtrip_efficiency
        simulated.raw_retention_days = retention.raw_retention_days
        simulated.public_meter_number = public_dashboard.meter_number
        return simulated

    latest = latest_measurements(_, db)
    purposes = _device_purposes(db)
    configs = _device_configs(db)
    device_count = db.query(Device).count()
    online_count = db.query(DeviceStatus).filter(DeviceStatus.online.is_(True)).count()
    current_total_power = None
    current_grid_power = None
    current_solar_power = None
    last_at = None

    for row in latest:
        if last_at is None or row.timestamp > last_at:
            last_at = row.timestamp
        if _is_grid_row(row, purposes):
            grid_value = _grid_power_value(row)
            if grid_value is not None:
                current_total_power = grid_value
                current_grid_power = grid_value
        if _is_solar_row(row, purposes):
            solar_value = _solar_power_value(row)
            if solar_value is not None:
                current_solar_power = (current_solar_power or 0.0) + solar_value

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    today_rows = db.query(Measurement).filter(Measurement.timestamp >= today).order_by(Measurement.timestamp.asc()).all()
    today_rows = [row for row in today_rows if _measurement_matches_device_config(row, configs)]
    grid_today_rows = [row for row in today_rows if _is_grid_row(row, purposes)]
    solar_today_rows = [row for row in today_rows if _is_solar_row(row, purposes)]

    imported_today_wh = delta_energy(grid_today_rows, 'energy_import_wh', None)
    exported_today_wh = delta_energy(grid_today_rows, 'energy_export_wh', None)
    solar_today_wh = delta_energy(solar_today_rows, 'energy_import_wh', None)

    imported_today_kwh = imported_today_wh / 1000 if imported_today_wh is not None else None
    exported_today_kwh = exported_today_wh / 1000 if exported_today_wh is not None else None
    solar_today_kwh = solar_today_wh / 1000 if solar_today_wh is not None else None
    imported_total_kwh, exported_total_kwh, solar_total_kwh = get_stored_total_kwh(
        db,
        (imported_today_kwh, exported_today_kwh, solar_today_kwh),
    )

    finance = get_finance_settings_from_db(db)
    retention = get_retention_settings_from_db(db)
    public_dashboard = get_public_dashboard_settings_from_db(db)
    price = finance.kwh_price_eur
    investment = finance.investment_cost_eur
    battery_enabled = finance.battery_analysis_enabled
    battery_cost = finance.battery_cost_eur
    battery_capacity = finance.battery_capacity_kwh

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

    battery = battery_analysis(
        exported_today_kwh,
        exported_total_kwh,
        kwh_price=price,
        battery_cost=battery_cost if battery_enabled else 0.0,
        battery_capacity_kwh=battery_capacity if battery_enabled else 0.0,
        battery_roundtrip_efficiency=finance.battery_roundtrip_efficiency,
        remaining_bps_investment=remaining,
    )

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
        battery_analysis_enabled=battery_enabled,
        battery_cost_eur=battery_cost,
        battery_capacity_kwh=battery_capacity,
        battery_roundtrip_efficiency=finance.battery_roundtrip_efficiency,
        battery_remaining_bps_investment_eur=battery['battery_remaining_bps_investment_eur'],
        battery_combined_investment_eur=battery['battery_combined_investment_eur'],
        battery_combined_payback_days=battery['battery_combined_payback_days'],
        battery_combined_payback_years=battery['battery_combined_payback_years'],
        battery_usable_surplus_today_kwh=battery['battery_usable_surplus_today_kwh'],
        battery_savings_today_eur=battery['battery_savings_today_eur'],
        battery_savings_total_potential_eur=battery['battery_savings_total_potential_eur'],
        battery_payback_days=battery['battery_payback_days'],
        battery_payback_years=battery['battery_payback_years'],
        battery_worthwhile=battery['battery_worthwhile'],
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
        public_meter_number=public_dashboard.meter_number,
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
    start, end = _clamp_live_window(start, end)
    rows = _raw_history_rows(db, start=start, end=end, limit=50000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['timestamp', 'device_id', 'source_type', 'channel', 'phase', 'power_w', 'voltage_v', 'current_a', 'power_factor', 'energy_import_wh', 'energy_export_wh', 'total_power_w'])
    for row in rows:
        writer.writerow([row.timestamp.isoformat(), row.device_id, row.source_type, row.channel, row.phase, row.power_w, row.voltage_v, row.current_a, row.power_factor, row.energy_import_wh, row.energy_export_wh, row.total_power_w])
    return Response(content=output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="bpstracker-measurements.csv"'})


@router.get('/public/summary', response_model=SummaryResponse)
def public_summary(db: Session = Depends(get_db)) -> SummaryResponse:
    _require_public_dashboard(db)
    return summary(None, db)  # type: ignore[arg-type]

