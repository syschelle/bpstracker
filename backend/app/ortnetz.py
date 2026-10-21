from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import AppSetting, Device, Measurement
from .routers.settings import ORTSNETZ_STATUS_KEY, get_ortnetz_settings_from_db
from .version import __version__

ORTSNETZ_URL = 'https://www.ortsnetz-auslastung.de/v1/measurements'
PHASE_SOURCES = {'shelly_3em_gen1_emeter', 'shelly_rpc_em'}
MAX_MEASUREMENT_AGE = timedelta(minutes=10)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_ortnetz_payload(db: Session, now: datetime | None = None) -> dict[str, Any] | None:
    settings = get_ortnetz_settings_from_db(db)
    if not settings.enabled or settings.device_id is None or settings.latitude is None or settings.longitude is None:
        return None

    simulation = db.get(AppSetting, 'simulation')
    if simulation and isinstance(simulation.value, dict) and simulation.value.get('enabled'):
        return None

    device = db.get(Device, settings.device_id)
    if device is None or not device.is_active:
        raise ValueError('Configured Ortsnetz meter is missing or inactive')

    latest_ts = (
        db.query(func.max(Measurement.timestamp))
        .filter(
            Measurement.device_id == device.id,
            Measurement.source_type.in_(PHASE_SOURCES),
            Measurement.phase.in_(['L1', 'L2', 'L3']),
        )
        .scalar()
    )
    if latest_ts is None:
        raise ValueError('No three-phase meter measurements available')

    reference_now = now or datetime.now(timezone.utc)
    comparable_ts = latest_ts if latest_ts.tzinfo else latest_ts.replace(tzinfo=timezone.utc)
    if reference_now - comparable_ts > MAX_MEASUREMENT_AGE:
        raise ValueError('Latest meter measurement is older than 10 minutes')

    rows = (
        db.query(Measurement)
        .filter(
            Measurement.device_id == device.id,
            Measurement.timestamp == latest_ts,
            Measurement.source_type.in_(PHASE_SOURCES),
            Measurement.phase.in_(['L1', 'L2', 'L3']),
        )
        .all()
    )
    phases: dict[str, Measurement] = {}
    for row in rows:
        if row.phase not in phases:
            phases[str(row.phase)] = row

    if not all(phase in phases for phase in ('L1', 'L2', 'L3')):
        raise ValueError('Latest meter sample does not contain L1, L2 and L3 from the same poll')
    if any(phases[p].voltage_v is None for p in ('L1', 'L2', 'L3')):
        raise ValueError('Latest meter sample is missing a phase voltage')

    payload: dict[str, Any] = {
        'observed_at': _iso_utc(comparable_ts),
        'latitude': settings.latitude,
        'longitude': settings.longitude,
        'l1_v': float(phases['L1'].voltage_v),
        'l2_v': float(phases['L2'].voltage_v),
        'l3_v': float(phases['L3'].voltage_v),
        'integration_version': f'bpstracker-{__version__}',
    }

    currents = [phases[p].current_a for p in ('L1', 'L2', 'L3')]
    for idx, value in enumerate(currents, start=1):
        if value is not None and value >= 0:
            payload[f'l{idx}_a'] = float(value)

    total_power = next((phases[p].total_power_w for p in ('L1', 'L2', 'L3') if phases[p].total_power_w is not None), None)
    if total_power is not None:
        payload['grid_power_w'] = float(total_power)

    if settings.plant_capacity_kwp is not None:
        payload['plant_capacity_kwp'] = float(settings.plant_capacity_kwp)
    if device.status and device.status.detected_model:
        payload['smartmeter_model'] = str(device.status.detected_model)[:120]
    return payload


def _save_status(db: Session, **updates: Any) -> None:
    row = db.get(AppSetting, ORTSNETZ_STATUS_KEY)
    value = dict(row.value) if row and isinstance(row.value, dict) else {}
    value.update(updates)
    if row is None:
        db.add(AppSetting(key=ORTSNETZ_STATUS_KEY, value=value))
    else:
        row.value = value
    db.commit()


async def send_ortnetz_measurement() -> None:
    attempted_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        try:
            payload = build_ortnetz_payload(db, attempted_at)
            if payload is None:
                return
            _save_status(db, last_attempt_at=_iso_utc(attempted_at), last_error=None)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            _save_status(db, last_attempt_at=_iso_utc(attempted_at), last_error=str(exc))
            return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(ORTSNETZ_URL, json=payload)
        body: dict[str, Any] | None
        try:
            parsed = response.json()
            body = parsed if isinstance(parsed, dict) else {'response': parsed}
        except Exception:  # noqa: BLE001
            body = {'text': response.text[:1000]} if response.text else None
        with SessionLocal() as db:
            if response.status_code == 202:
                _save_status(
                    db,
                    last_success_at=_iso_utc(datetime.now(timezone.utc)),
                    last_http_status=response.status_code,
                    last_response=body,
                    last_error=None,
                )
            else:
                _save_status(
                    db,
                    last_http_status=response.status_code,
                    last_response=body,
                    last_error=f'Ortsnetz API returned HTTP {response.status_code}',
                )
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            _save_status(db, last_error=str(exc))
