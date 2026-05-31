from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..energy_retention import (
    GRID_ENERGY_SOURCES,
    SOLAR_ENERGY_SOURCES,
    delta_energy,
    ensure_completed_daily_summaries,
    get_stored_total_kwh,
)
from ..models import AppSetting, Device, Measurement
from ..simulation import simulated_values_at

router = APIRouter(prefix='/api/current-values', tags=['current-values'])

GRID_POWER_SOURCES = {'shelly_3em_gen1_total', 'shelly_rpc_em_total'}
UI_SETTINGS_KEY = 'ui'
CURRENT_VALUES_API_SETTINGS_KEY = 'current_values_api'
SIMULATION_SETTINGS_KEY = 'simulation'
DEFAULT_TIMEZONE = 'Europe/Berlin'

DEVICE_PURPOSE_AUTO = 'auto'
DEVICE_PURPOSE_GRID = 'grid'
DEVICE_PURPOSE_SOLAR = 'solar'
DEVICE_PURPOSE_IGNORED = 'ignored'


def _device_purposes(db: Session) -> dict[int, str]:
    rows = db.query(Device.id, Device.purpose).all()
    return {int(device_id): str(purpose or DEVICE_PURPOSE_AUTO) for device_id, purpose in rows}


def _purpose_for(row: Measurement, purposes: dict[int, str]) -> str:
    return purposes.get(int(row.device_id), DEVICE_PURPOSE_AUTO)


def _is_solar_row(row: Measurement, purposes: dict[int, str]) -> bool:
    purpose = _purpose_for(row, purposes)
    if purpose == DEVICE_PURPOSE_IGNORED:
        return False
    if purpose == DEVICE_PURPOSE_SOLAR:
        return True
    return purpose == DEVICE_PURPOSE_AUTO and row.source_type in SOLAR_ENERGY_SOURCES


def _is_grid_row(row: Measurement, purposes: dict[int, str]) -> bool:
    purpose = _purpose_for(row, purposes)
    if purpose == DEVICE_PURPOSE_IGNORED:
        return False
    if purpose == DEVICE_PURPOSE_GRID:
        return True
    return purpose == DEVICE_PURPOSE_AUTO and row.source_type in (GRID_POWER_SOURCES | GRID_ENERGY_SOURCES)


def _solar_power_value(row: Measurement) -> float | None:
    value = row.power_w if row.power_w is not None else row.total_power_w
    return abs(value) if value is not None else None


def _grid_power_value(row: Measurement) -> float | None:
    if row.total_power_w is not None:
        return row.total_power_w
    return row.power_w



def _simulation_enabled(db: Session) -> bool:
    row = db.get(AppSetting, SIMULATION_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    return bool(value.get('enabled', False))


def _api_enabled(db: Session) -> bool:
    row = db.get(AppSetting, CURRENT_VALUES_API_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    return bool(value.get('enabled', False))


def _ui_timezone(db: Session) -> str:
    row = db.get(AppSetting, UI_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    timezone_name = str(value.get('timezone') or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = DEFAULT_TIMEZONE
    return timezone_name


def _zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _latest_measurements(db: Session) -> list[Measurement]:
    subq = (
        db.query(
            Measurement.device_id,
            Measurement.source_type,
            Measurement.channel,
            Measurement.phase,
            func.max(Measurement.timestamp).label('max_ts'),
        )
        .group_by(Measurement.device_id, Measurement.source_type, Measurement.channel, Measurement.phase)
        .subquery()
    )
    return (
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


def _today_bounds_utc(timezone_name: str) -> tuple[datetime, datetime, str]:
    tz = _zoneinfo(timezone_name)
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), now_local.date().isoformat()


def _kwh(value_wh: float | None) -> float | None:
    return value_wh / 1000.0 if value_wh is not None else None


@router.get('', summary='Current BPSTracker values as JSON')
@router.get('/', include_in_schema=False)
def current_values(db: Session = Depends(get_db)) -> dict:
    """Return current and accumulated BPSTracker values as plain JSON.

    The response intentionally uses stable English field names so it can be
    consumed by home automation systems, scripts, dashboards or other local
    integrations. The endpoint returns numeric values; units are encoded in the
    field names.
    """
    if not _api_enabled(db):
        raise HTTPException(status_code=503, detail='Current values API is disabled in setup')

    timezone_name = _ui_timezone(db)
    now_utc = datetime.now(timezone.utc)
    if _simulation_enabled(db):
        values = simulated_values_at(now_utc, timezone_name)
        return {
            'timestamp_utc': now_utc.isoformat(),
            'local_date': now_utc.astimezone(_zoneinfo(timezone_name)).date().isoformat(),
            'timezone': timezone_name,
            'simulation_enabled': True,
            'simulation_profile': '800 W balcony PV, 2-person household',
            'last_measurement_at': values.timestamp.isoformat(),
            'current_solar_production_w': values.solar_w,
            'current_grid_power_w': values.grid_w,
            'current_grid_import_w': max(0.0, values.grid_w),
            'current_grid_export_w': abs(min(0.0, values.grid_w)),
            'current_total_consumption_w': values.consumption_w,
            'daily_solar_production_kwh': values.solar_today_kwh,
            'daily_grid_import_kwh': values.import_today_kwh,
            'daily_grid_export_kwh': values.export_today_kwh,
            'total_solar_production_kwh': values.solar_total_kwh,
            'total_grid_import_kwh': values.import_total_kwh,
            'total_grid_export_kwh': values.export_total_kwh,
        }

    latest = _latest_measurements(db)

    current_grid_power_w = None
    current_solar_power_w = None
    last_measurement_at = None

    for row in latest:
        if last_measurement_at is None or row.timestamp > last_measurement_at:
            last_measurement_at = row.timestamp

        if row.source_type in GRID_POWER_SOURCES and row.total_power_w is not None:
            current_grid_power_w = row.total_power_w

        if row.source_type in SOLAR_ENERGY_SOURCES and row.power_w is not None:
            current_solar_power_w = (current_solar_power_w or 0.0) + abs(row.power_w)

    # Signed grid power: positive means import, negative means export.
    signed_grid_power_w = current_grid_power_w
    current_grid_import_w = max(0.0, signed_grid_power_w or 0.0)
    current_grid_export_w = abs(min(0.0, signed_grid_power_w or 0.0))
    current_solar_power_w = current_solar_power_w if current_solar_power_w is not None else 0.0

    # Estimated current total house consumption:
    # grid import + solar production. If the grid value is negative, the current
    # grid import is zero and export is reported separately.
    current_total_consumption_w = current_grid_import_w + current_solar_power_w

    today_start_utc, today_end_utc, local_date = _today_bounds_utc(timezone_name)

    ensure_completed_daily_summaries(db, now_utc)

    today_rows = (
        db.query(Measurement)
        .filter(Measurement.timestamp >= today_start_utc, Measurement.timestamp < today_end_utc)
        .order_by(Measurement.timestamp.asc())
        .all()
    )

    daily_grid_import_kwh = _kwh(delta_energy(today_rows, 'energy_import_wh', GRID_ENERGY_SOURCES))
    daily_grid_export_kwh = _kwh(delta_energy(today_rows, 'energy_export_wh', GRID_ENERGY_SOURCES))
    daily_solar_production_kwh = _kwh(delta_energy(today_rows, 'energy_import_wh', SOLAR_ENERGY_SOURCES))

    total_grid_import_kwh, total_grid_export_kwh, total_solar_production_kwh = get_stored_total_kwh(
        db,
        (daily_grid_import_kwh, daily_grid_export_kwh, daily_solar_production_kwh),
    )

    return {
        'timestamp_utc': now_utc.isoformat(),
        'local_date': local_date,
        'timezone': timezone_name,
        'last_measurement_at': last_measurement_at.isoformat() if last_measurement_at else None,

        'current_solar_production_w': current_solar_power_w,
        'current_grid_power_w': signed_grid_power_w,
        'current_grid_import_w': current_grid_import_w,
        'current_grid_export_w': current_grid_export_w,
        'current_total_consumption_w': current_total_consumption_w,

        'daily_solar_production_kwh': daily_solar_production_kwh,
        'daily_grid_import_kwh': daily_grid_import_kwh,
        'daily_grid_export_kwh': daily_grid_export_kwh,

        'total_solar_production_kwh': total_solar_production_kwh,
        'total_grid_import_kwh': total_grid_import_kwh,
        'total_grid_export_kwh': total_grid_export_kwh,
    }
