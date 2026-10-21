from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
import math
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AppSetting, AuditLog, User
from ..schemas import AirSensorCurrent, AirSensorSettings, CurrentValuesApiSettings, OrtnetzSettings, OrtnetzStatus, PublicDashboardSettings, FinanceSettings, KindleDisplaySettings, RetentionSettings, SimulationSettings, UiSettings
from ..network_security import OutboundHostError, lan_http_url, normalize_outbound_http_host, resolve_lan_http_target
from ..security import decrypt_secret, encrypt_secret, get_current_user, require_admin
from ..simulation import simulated_air_sensor_current

router = APIRouter(prefix='/api/settings', tags=['settings'])
logger = logging.getLogger(__name__)

FINANCE_SETTINGS_KEY = 'finance'
UI_SETTINGS_KEY = 'ui'
RETENTION_SETTINGS_KEY = 'retention'
AIR_SENSOR_SETTINGS_KEY = 'air_sensor'
KINDLE_DISPLAY_SETTINGS_KEY = 'kindle_display'
CURRENT_VALUES_API_SETTINGS_KEY = 'current_values_api'
PUBLIC_DASHBOARD_SETTINGS_KEY = 'public_dashboard'
ORTSNETZ_SETTINGS_KEY = 'ortnetz'
ORTSNETZ_STATUS_KEY = 'ortnetz_status'
SIMULATION_SETTINGS_KEY = 'simulation'
SIMULATION_CACHE_KEY = 'simulation_cache'
AIR_SENSOR_CACHE_KEY = 'air_sensor_cache'
AIR_SENSOR_SUCCESS_POLL_SECONDS = 180
AIR_SENSOR_RETRY_SECONDS = 30
WEATHER_UNDERGROUND_UPLOAD_URL = 'https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php'
LEGACY_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE_NO_DEWPOINT = (
    WEATHER_UNDERGROUND_UPLOAD_URL
    + '?ID={station_id}&PASSWORD={api_key}&dateutc={dateutc}&action=updateraw'
    + '&softwaretype={softwaretype}&realtime=1&rtfreq={rtfreq}'
    + '&tempf={tempf}&humidity={humidity}&baromin={baromin}&AqPM2.5={pm25}&AqPM10={pm10}'
)
DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE = (
    WEATHER_UNDERGROUND_UPLOAD_URL
    + '?ID={station_id}&PASSWORD={api_key}&dateutc={dateutc}&action=updateraw'
    + '&softwaretype={softwaretype}&realtime=1&rtfreq={rtfreq}'
    + '&tempf={tempf}&humidity={humidity}&dewptf={dewptf}&baromin={baromin}&AqPM2.5={pm25}&AqPM10={pm10}'
)
DEFAULT_KWH_PRICE_EUR = 0.30
DEFAULT_INVESTMENT_COST_EUR = 0.0
DEFAULT_BATTERY_ROUNDTRIP_EFFICIENCY = 0.85
DEFAULT_LANGUAGE = 'de'
LANGUAGE_RE = re.compile(r'^[a-z]{2}([_-][a-z0-9]+)?$')


def get_default_language() -> str:
    language = str(get_settings().default_language or DEFAULT_LANGUAGE).strip().lower()
    return language if LANGUAGE_RE.fullmatch(language) else DEFAULT_LANGUAGE


DEFAULT_CURRENCY_CODE = 'EUR'
DEFAULT_TIMEZONE = 'Europe/Berlin'
DEFAULT_RAW_RETENTION_DAYS = 30
DEFAULT_PUBLIC_METER_NUMBER: str | None = None
ALLOWED_CURRENCIES = {'EUR', 'USD', 'GBP'}


def _positive_int_or_none(value: object, *, max_value: int = 3650 * 24) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return max(1, min(max_value, parsed))


def get_raw_retention_hours_override() -> int | None:
    settings = get_settings()
    configured = _positive_int_or_none(settings.raw_retention_hours)
    if configured is not None:
        return configured
    if settings.pi_zero_2w_mode:
        return 24
    return None


def get_live_data_max_hours() -> int | None:
    settings = get_settings()
    configured = _positive_int_or_none(settings.live_data_max_hours)
    if configured is not None:
        return configured
    if settings.pi_zero_2w_mode:
        return 24
    return None


def _normalize_host(value: str | None) -> str | None:
    try:
        return normalize_outbound_http_host(value)
    except OutboundHostError:
        # Reading settings should not crash if an older database contains an invalid
        # value. Admin updates and outbound fetches perform strict validation.
        return str(value).strip() if value else None


def _normalize_host_or_400(value: str | None) -> str | None:
    try:
        return normalize_outbound_http_host(value)
    except OutboundHostError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc





def _normalize_meter_number(value: object) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    # Keep it printable and compact for the public smart-meter display.
    return text[:80]

def _normalize_battery_efficiency(value: object) -> float:
    try:
        efficiency = float(value)
    except (TypeError, ValueError):
        return DEFAULT_BATTERY_ROUNDTRIP_EFFICIENCY
    if efficiency <= 0:
        return DEFAULT_BATTERY_ROUNDTRIP_EFFICIENCY
    return min(1.0, max(0.5, efficiency))

def _normalize_timezone(value: object) -> str:
    timezone_name = str(value or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    # Accept only real IANA timezones. ZoneInfo handles DST/summer-/winter-time rules.
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = DEFAULT_TIMEZONE
    return timezone_name


def _normalize_ui_value(value: dict | None) -> UiSettings:
    value = value or {}
    default_language = get_default_language()
    language = str(value.get('language', default_language) or default_language).lower()
    if not LANGUAGE_RE.fullmatch(language):
        language = default_language
    return UiSettings(language=language, timezone=_normalize_timezone(value.get('timezone', DEFAULT_TIMEZONE)))


def get_ui_settings_from_db(db: Session) -> UiSettings:
    row = db.get(AppSetting, UI_SETTINGS_KEY)
    return _normalize_ui_value(row.value if row else None)


def _normalize_finance_value(value: dict | None) -> FinanceSettings:
    value = value or {}
    currency_code = str(value.get('currency_code', DEFAULT_CURRENCY_CODE) or DEFAULT_CURRENCY_CODE).upper()
    if currency_code not in ALLOWED_CURRENCIES:
        currency_code = DEFAULT_CURRENCY_CODE
    return FinanceSettings(
        kwh_price_eur=float(value.get('kwh_price_eur', DEFAULT_KWH_PRICE_EUR) or 0.0),
        investment_cost_eur=float(value.get('investment_cost_eur', DEFAULT_INVESTMENT_COST_EUR) or 0.0),
        battery_analysis_enabled=bool(value.get('battery_analysis_enabled', False)),
        battery_cost_eur=float(value.get('battery_cost_eur', 0.0) or 0.0),
        battery_capacity_kwh=float(value.get('battery_capacity_kwh', 0.0) or 0.0),
        battery_roundtrip_efficiency=_normalize_battery_efficiency(value.get('battery_roundtrip_efficiency', DEFAULT_BATTERY_ROUNDTRIP_EFFICIENCY)),
        currency_code=currency_code,
    )


def get_finance_settings_from_db(db: Session) -> FinanceSettings:
    row = db.get(AppSetting, FINANCE_SETTINGS_KEY)
    return _normalize_finance_value(row.value if row else None)




def _normalize_air_sensor_value(value: dict | None) -> AirSensorSettings:
    value = value or {}
    station_id = str(value.get('weather_underground_station_id') or '').strip().upper() or None
    api_key_ciphertext = str(value.get('weather_underground_api_key_ciphertext') or '').strip()
    upload_url = str(value.get('weather_underground_upload_url') or '').strip() or DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE
    if upload_url == LEGACY_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE_NO_DEWPOINT:
        upload_url = DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE
    return AirSensorSettings(
        enabled=bool(value.get('enabled', False)),
        host=_normalize_host(value.get('host')),
        altitude_m=_air_sensor_altitude_m(value.get('altitude_m')),
        weather_underground_enabled=bool(value.get('weather_underground_enabled', False)),
        weather_underground_station_id=station_id,
        weather_underground_api_key=None,
        weather_underground_api_key_set=bool(api_key_ciphertext),
        weather_underground_upload_url=upload_url,
    )


def get_air_sensor_settings_from_db(db: Session) -> AirSensorSettings:
    row = db.get(AppSetting, AIR_SENSOR_SETTINGS_KEY)
    return _normalize_air_sensor_value(row.value if row else None)


def _float_from_value(value: object) -> float | None:
    try:
        if value is None or value == '':
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _int_from_value(value: object) -> int | None:
    try:
        if value is None or value == '':
            return None
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _bool_from_value(value: object) -> bool | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'ja'}:
        return True
    if normalized in {'0', 'false', 'no', 'nein'}:
        return False
    return None


def _pressure_hpa_from_value(value: object) -> float | None:
    pressure = _float_from_value(value)
    if pressure is None:
        return None
    if pressure > 2000:
        return pressure / 100.0
    return pressure


def _air_sensor_altitude_m(value: object) -> float | None:
    altitude = _float_from_value(value)
    if altitude is None:
        return None
    return max(-500.0, min(9000.0, altitude))


def _sea_level_pressure_hpa(pressure_hpa: float | None, altitude_m: float | None) -> float | None:
    if pressure_hpa is None:
        return None
    if altitude_m is None or altitude_m == 0:
        return round(pressure_hpa, 1)
    return round(pressure_hpa / ((1.0 - (altitude_m / 44330.0)) ** 5.255), 1)


def _datetime_from_value(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _air_sensor_cache_value(db: Session) -> dict:
    row = db.get(AppSetting, AIR_SENSOR_CACHE_KEY)
    value = row.value if row else {}
    return value if isinstance(value, dict) else {}


def _air_sensor_has_values(current: AirSensorCurrent) -> bool:
    return any(getattr(current, field) is not None for field in ('temperature_c', 'humidity_percent', 'pressure_hpa', 'sds_p1', 'sds_p2'))


def _air_sensor_cache_from_db(db: Session, settings: AirSensorSettings, configured: bool, *, ok: bool = False, last_error: str | None = None) -> AirSensorCurrent:
    value = _air_sensor_cache_value(db)
    stored_error = str(value.get('last_error')) if value.get('last_error') else None
    pressure_hpa = _float_from_value(value.get('pressure_hpa'))
    return AirSensorCurrent(
        enabled=settings.enabled,
        configured=configured,
        ok=ok,
        cached=bool(value),
        temperature_c=_float_from_value(value.get('temperature_c')),
        humidity_percent=_float_from_value(value.get('humidity_percent')),
        dew_point_c=_float_from_value(value.get('dew_point_c')),
        pressure_hpa=pressure_hpa,
        pressure_sea_level_hpa=_sea_level_pressure_hpa(pressure_hpa, settings.altitude_m),
        sds_p1=_float_from_value(value.get('sds_p1')),
        sds_p2=_float_from_value(value.get('sds_p2')),
        age_seconds=_int_from_value(value.get('age_seconds')),
        software_version=str(value.get('software_version')) if value.get('software_version') else None,
        last_success_at=_datetime_from_value(value.get('last_success_at')),
        last_error=last_error if last_error is not None else (stored_error if not ok else None),
        weather_underground_last_ok=_bool_from_value(value.get('weather_underground_last_ok')),
        weather_underground_last_status=_int_from_value(value.get('weather_underground_last_status')),
        weather_underground_last_response=str(value.get('weather_underground_last_response')) if value.get('weather_underground_last_response') else None,
        weather_underground_last_at=_datetime_from_value(value.get('weather_underground_last_at')),
    )


def get_cached_air_sensor_current(settings: AirSensorSettings, db: Session) -> AirSensorCurrent:
    configured = bool(settings.host)
    if not settings.enabled or not configured:
        return AirSensorCurrent(enabled=settings.enabled, configured=configured, ok=False)

    cached_value = _air_sensor_cache_value(db)
    current = _air_sensor_cache_from_db(db, settings, configured)
    stored_error = str(cached_value.get('last_error')) if cached_value.get('last_error') else None
    return _air_sensor_cache_from_db(
        db,
        settings,
        configured,
        ok=not stored_error and _air_sensor_has_values(current),
        last_error=stored_error,
    )


def _upsert_air_sensor_cache_value(db: Session, value: dict) -> None:
    row = db.get(AppSetting, AIR_SENSOR_CACHE_KEY)
    if row is None:
        row = AppSetting(key=AIR_SENSOR_CACHE_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def _save_air_sensor_cache(db: Session, current: AirSensorCurrent, *, last_attempt_at: datetime | None = None) -> None:
    value = current.model_dump(mode='json')
    value.pop('enabled', None)
    value.pop('configured', None)
    value.pop('ok', None)
    value.pop('cached', None)
    value.pop('last_error', None)
    if last_attempt_at is not None:
        value['last_attempt_at'] = last_attempt_at.isoformat()
    value.pop('last_error', None)
    _upsert_air_sensor_cache_value(db, value)


def _save_air_sensor_failure(db: Session, message: str, *, last_attempt_at: datetime) -> None:
    value = _air_sensor_cache_value(db)
    value['last_attempt_at'] = last_attempt_at.isoformat()
    value['last_error'] = message
    _upsert_air_sensor_cache_value(db, value)


def _merge_with_previous(current: AirSensorCurrent, previous: AirSensorCurrent) -> AirSensorCurrent:
    # Keep the last good value for individual fields that are temporarily missing.
    for field in ('temperature_c', 'humidity_percent', 'dew_point_c', 'pressure_hpa', 'pressure_sea_level_hpa', 'sds_p1', 'sds_p2', 'age_seconds', 'software_version'):
        if getattr(current, field) is None and getattr(previous, field) is not None:
            setattr(current, field, getattr(previous, field))
    return current


def _weather_underground_api_key_from_db(db: Session) -> str | None:
    row = db.get(AppSetting, AIR_SENSOR_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    ciphertext = value.get('weather_underground_api_key_ciphertext')
    return decrypt_secret(str(ciphertext)) if ciphertext else None


def _apply_weather_underground_api_key_update(raw_value: dict, existing_value: dict) -> bool:
    api_key = str(raw_value.pop('weather_underground_api_key', None) or '').strip()
    if api_key:
        raw_value['weather_underground_api_key_ciphertext'] = encrypt_secret(api_key)
    elif existing_value.get('weather_underground_api_key_ciphertext'):
        raw_value['weather_underground_api_key_ciphertext'] = existing_value.get('weather_underground_api_key_ciphertext')
    raw_value.pop('weather_underground_api_key_set', None)
    return bool(api_key)


def _fahrenheit(celsius: float) -> float:
    return (celsius * 9.0 / 5.0) + 32.0


def _inches_hg(hpa: float) -> float:
    return hpa * 0.0295299830714


def _dew_point_c(temperature_c: float | None, humidity_percent: float | None) -> float | None:
    if temperature_c is None or humidity_percent is None or humidity_percent <= 0:
        return None
    humidity = min(100.0, max(0.1, humidity_percent))
    alpha = math.log(humidity / 100.0) + (17.62 * temperature_c) / (243.12 + temperature_c)
    return round((243.12 * alpha) / (17.62 - alpha), 1)


def _weather_underground_params(settings: AirSensorSettings, current: AirSensorCurrent, api_key: str, now: datetime) -> dict[str, str]:
    params: dict[str, str] = {
        'ID': str(settings.weather_underground_station_id or '').strip().upper(),
        'PASSWORD': api_key,
        'dateutc': now.strftime('%Y-%m-%d %H:%M:%S'),
        'action': 'updateraw',
        'softwaretype': 'BPSTracker',
        'realtime': '1',
        'rtfreq': str(AIR_SENSOR_SUCCESS_POLL_SECONDS),
    }
    if current.temperature_c is not None:
        params['tempf'] = f'{_fahrenheit(current.temperature_c):.2f}'
    if current.humidity_percent is not None:
        params['humidity'] = str(max(0, min(100, int(round(current.humidity_percent)))))
    if current.dew_point_c is not None:
        params['dewptf'] = f'{_fahrenheit(current.dew_point_c):.1f}'
    pressure_for_weather_underground = current.pressure_sea_level_hpa if current.pressure_sea_level_hpa is not None else current.pressure_hpa
    if pressure_for_weather_underground is not None:
        params['baromin'] = f'{_inches_hg(pressure_for_weather_underground):.2f}'
    if current.sds_p2 is not None:
        params['AqPM2.5'] = f'{current.sds_p2:.2f}'
    if current.sds_p1 is not None:
        params['AqPM10'] = f'{current.sds_p1:.2f}'
    return params


def _weather_underground_upload_url(settings: AirSensorSettings, current: AirSensorCurrent, api_key: str, now: datetime) -> str:
    params = _weather_underground_params(settings, current, api_key, now)
    values = {
        'station_id': params.get('ID', ''),
        'api_key': params.get('PASSWORD', ''),
        'dateutc': params.get('dateutc', ''),
        'softwaretype': params.get('softwaretype', ''),
        'rtfreq': params.get('rtfreq', ''),
        'tempf': params.get('tempf', ''),
        'humidity': params.get('humidity', ''),
        'dewptf': params.get('dewptf', ''),
        'baromin': params.get('baromin', ''),
        'pm25': params.get('AqPM2.5', ''),
        'pm10': params.get('AqPM10', ''),
    }
    url = settings.weather_underground_upload_url or DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE
    for key, value in values.items():
        url = url.replace('{' + key + '}', quote_plus(str(value)))
    return url


def _weather_underground_status(ok: bool, now: datetime, *, status: int | None = None, response: str | None = None) -> dict[str, object]:
    cleaned_response = str(response or '').strip()
    return {
        'weather_underground_last_ok': ok,
        'weather_underground_last_status': status,
        'weather_underground_last_response': cleaned_response[:240] or None,
        'weather_underground_last_at': now,
    }


def _apply_weather_underground_status(current: AirSensorCurrent, status: dict[str, object] | None) -> None:
    if not status:
        return
    for key, value in status.items():
        setattr(current, key, value)


async def _upload_weather_underground(settings: AirSensorSettings, current: AirSensorCurrent, db: Session, now: datetime) -> dict[str, object] | None:
    if not settings.weather_underground_enabled or not settings.weather_underground_station_id:
        return None
    api_key = _weather_underground_api_key_from_db(db)
    if not api_key:
        return _weather_underground_status(False, now, response='Missing Weather Underground key')
    upload_url = _weather_underground_upload_url(settings, current, api_key, now)
    timeout = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(upload_url)
            response_text = response.text.strip()
            if response.is_error:
                logger.warning('Weather Underground upload failed with HTTP %s: %s', response.status_code, response_text)
                return _weather_underground_status(False, now, status=response.status_code, response=response_text or response.reason_phrase)
            ok = not response_text or response_text.lower().startswith('success')
            if not ok:
                logger.warning('Weather Underground upload returned: %s', response_text)
            return _weather_underground_status(ok, now, status=response.status_code, response=response_text or response.reason_phrase)
    except Exception as exc:
        logger.warning('Weather Underground upload failed: %s', exc.__class__.__name__)
        return _weather_underground_status(False, now, response=exc.__class__.__name__)


async def fetch_air_sensor_current(settings: AirSensorSettings, db: Session) -> AirSensorCurrent:
    configured = bool(settings.host)
    if not settings.enabled or not configured:
        return AirSensorCurrent(enabled=settings.enabled, configured=configured, ok=False)

    now = datetime.now(timezone.utc)
    cached_value = _air_sensor_cache_value(db)
    previous = _air_sensor_cache_from_db(db, settings, configured)
    last_success_at = _datetime_from_value(cached_value.get('last_success_at'))
    last_attempt_at = _datetime_from_value(cached_value.get('last_attempt_at'))
    stored_error = str(cached_value.get('last_error')) if cached_value.get('last_error') else None

    # The Luftdaten firmware typically refreshes its own measurements every 180 seconds.
    # After a successful read, do not hit the sensor more often than that. The frontend may
    # ask more frequently, but this endpoint returns the cached value until the 180 seconds
    # have passed.
    if last_success_at and (now - last_success_at).total_seconds() < AIR_SENSOR_SUCCESS_POLL_SECONDS and _air_sensor_has_values(previous):
        return _air_sensor_cache_from_db(db, settings, configured, ok=True)

    # If the last attempt failed, retry faster than the normal 180 second interval, but still
    # throttle retries so a slow/offline sensor cannot block or flood the application.
    if stored_error and last_attempt_at and (now - last_attempt_at).total_seconds() < AIR_SENSOR_RETRY_SECONDS:
        return _air_sensor_cache_from_db(db, settings, configured, ok=False, last_error=stored_error)

    timeout = httpx.Timeout(connect=1.0, read=3.0, write=1.0, pool=1.0)
    try:
        target = resolve_lan_http_target(settings.host or '')
        url = lan_http_url(target, '/data.json')
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(url, headers={'Host': target.host_header})
            if response.is_redirect:
                location = response.headers.get('location', '')
                raise OutboundHostError(f'Redirect blockiert: {location}')
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # network/device errors should not break the dashboard
        message = f'Luftdatensensor nicht erreichbar: {exc}'
        _save_air_sensor_failure(db, message, last_attempt_at=now)
        return _air_sensor_cache_from_db(db, settings, configured, ok=False, last_error=message)

    values: dict[str, object] = {}
    for item in payload.get('sensordatavalues', []) or []:
        if not isinstance(item, dict):
            continue
        key = item.get('value_type')
        if key:
            values[str(key)] = item.get('value')

    temperature = (
        _float_from_value(values.get('BME280_temperature'))
        or _float_from_value(values.get('BMP280_temperature'))
        or _float_from_value(values.get('temperature'))
    )
    humidity = (
        _float_from_value(values.get('BME280_humidity'))
        or _float_from_value(values.get('humidity'))
    )
    pressure = (
        _pressure_hpa_from_value(values.get('BME280_pressure'))
        or _pressure_hpa_from_value(values.get('BMP280_pressure'))
        or _pressure_hpa_from_value(values.get('pressure'))
    )

    current = AirSensorCurrent(
        enabled=settings.enabled,
        configured=configured,
        ok=True,
        cached=False,
        temperature_c=temperature,
        humidity_percent=humidity,
        dew_point_c=_dew_point_c(temperature, humidity),
        pressure_hpa=pressure,
        pressure_sea_level_hpa=_sea_level_pressure_hpa(pressure, settings.altitude_m),
        sds_p1=_float_from_value(values.get('SDS_P1')),
        sds_p2=_float_from_value(values.get('SDS_P2')),
        age_seconds=_int_from_value(payload.get('age')),
        software_version=str(payload.get('software_version')) if payload.get('software_version') else None,
        last_success_at=now,
    )
    current = _merge_with_previous(current, previous)

    if not _air_sensor_has_values(current):
        message = 'Luftdatensensor lieferte keine verwertbaren Werte.'
        _save_air_sensor_failure(db, message, last_attempt_at=now)
        return _air_sensor_cache_from_db(db, settings, configured, ok=False, last_error=message)

    _apply_weather_underground_status(current, await _upload_weather_underground(settings, current, db, now))
    _save_air_sensor_cache(db, current, last_attempt_at=now)
    return current


def _normalize_retention_value(value: dict | None) -> RetentionSettings:
    value = value or {}
    try:
        raw_days = int(value.get('raw_retention_days', DEFAULT_RAW_RETENTION_DAYS) or DEFAULT_RAW_RETENTION_DAYS)
    except (TypeError, ValueError):
        raw_days = DEFAULT_RAW_RETENTION_DAYS
    raw_days = max(7, min(3650, raw_days))
    raw_hours_override = get_raw_retention_hours_override()
    live_hours = get_live_data_max_hours()
    effective_hours = raw_hours_override if raw_hours_override is not None else raw_days * 24
    return RetentionSettings(
        raw_retention_days=raw_days,
        daily_aggregates_forever=True,
        effective_raw_retention_hours=effective_hours,
        live_data_max_hours=live_hours,
        pi_zero_2w_mode=get_settings().pi_zero_2w_mode,
    )


def get_retention_settings_from_db(db: Session) -> RetentionSettings:
    row = db.get(AppSetting, RETENTION_SETTINGS_KEY)
    return _normalize_retention_value(row.value if row else None)


def _normalize_kindle_display_value(value: dict | None) -> KindleDisplaySettings:
    value = value or {}
    return KindleDisplaySettings(enabled=bool(value.get('enabled', True)))


def get_kindle_display_settings_from_db(db: Session) -> KindleDisplaySettings:
    row = db.get(AppSetting, KINDLE_DISPLAY_SETTINGS_KEY)
    return _normalize_kindle_display_value(row.value if row else None)


def _normalize_current_values_api_value(value: dict | None) -> CurrentValuesApiSettings:
    value = value or {}
    return CurrentValuesApiSettings(enabled=bool(value.get('enabled', False)))


def _normalize_public_dashboard_value(value: dict | None) -> PublicDashboardSettings:
    value = value or {}
    return PublicDashboardSettings(
        enabled=bool(value.get('enabled', False)),
        meter_number=_normalize_meter_number(value.get('meter_number', DEFAULT_PUBLIC_METER_NUMBER)),
    )


def get_public_dashboard_settings_from_db(db: Session) -> PublicDashboardSettings:
    row = db.get(AppSetting, PUBLIC_DASHBOARD_SETTINGS_KEY)
    return _normalize_public_dashboard_value(row.value if row else None)


def _normalize_ortnetz_value(value: dict | None) -> OrtnetzSettings:
    value = value or {}
    return OrtnetzSettings(
        enabled=bool(value.get('enabled', False)),
        device_id=value.get('device_id'),
        latitude=value.get('latitude'),
        longitude=value.get('longitude'),
        plant_capacity_kwp=value.get('plant_capacity_kwp'),
    )


def get_ortnetz_settings_from_db(db: Session) -> OrtnetzSettings:
    row = db.get(AppSetting, ORTSNETZ_SETTINGS_KEY)
    return _normalize_ortnetz_value(row.value if row else None)


def get_ortnetz_status_from_db(db: Session) -> OrtnetzStatus:
    row = db.get(AppSetting, ORTSNETZ_STATUS_KEY)
    value = dict(row.value) if row and isinstance(row.value, dict) else {}
    value['enabled'] = get_ortnetz_settings_from_db(db).enabled
    return OrtnetzStatus(**value)


def get_current_values_api_settings_from_db(db: Session) -> CurrentValuesApiSettings:
    row = db.get(AppSetting, CURRENT_VALUES_API_SETTINGS_KEY)
    return _normalize_current_values_api_value(row.value if row else None)


def _normalize_simulation_value(value: dict | None) -> SimulationSettings:
    value = value or {}
    try:
        pv_peak_w = float(value.get('pv_peak_w', 800.0) or 800.0)
    except (TypeError, ValueError):
        pv_peak_w = 800.0
    try:
        baseload_day_w = float(value.get('baseload_day_w', 155.0) or 0.0)
    except (TypeError, ValueError):
        baseload_day_w = 155.0
    try:
        baseload_night_w = float(value.get('baseload_night_w', 90.0) or 0.0)
    except (TypeError, ValueError):
        baseload_night_w = 90.0
    pv_peak_w = min(5000.0, max(100.0, pv_peak_w))
    baseload_day_w = min(5000.0, max(0.0, baseload_day_w))
    baseload_night_w = min(5000.0, max(0.0, baseload_night_w))
    return SimulationSettings(
        enabled=bool(value.get('enabled', False)),
        pv_peak_w=pv_peak_w,
        baseload_day_w=baseload_day_w,
        baseload_night_w=baseload_night_w,
        household_profile=str(value.get('household_profile') or 'two_person_household'),
    )


def get_simulation_settings_from_db(db: Session) -> SimulationSettings:
    row = db.get(AppSetting, SIMULATION_SETTINGS_KEY)
    return _normalize_simulation_value(row.value if row else None)


@router.get('/ui', response_model=UiSettings)
def get_ui_settings(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UiSettings:
    return get_ui_settings_from_db(db)


@router.put('/ui', response_model=UiSettings)
def update_ui_settings(
    payload: UiSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UiSettings:
    normalized = _normalize_ui_value(payload.model_dump())
    row = db.get(AppSetting, UI_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=UI_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.ui.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_ui_value(row.value)


@router.get('/finance', response_model=FinanceSettings)
def get_finance_settings(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FinanceSettings:
    return get_finance_settings_from_db(db)


@router.put('/finance', response_model=FinanceSettings)
def update_finance_settings(
    payload: FinanceSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FinanceSettings:
    row = db.get(AppSetting, FINANCE_SETTINGS_KEY)
    normalized = _normalize_finance_value(payload.model_dump())
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=FINANCE_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.finance.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_finance_value(row.value)


@router.get('/retention', response_model=RetentionSettings)
def get_retention_settings(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RetentionSettings:
    return get_retention_settings_from_db(db)


@router.put('/retention', response_model=RetentionSettings)
def update_retention_settings(
    payload: RetentionSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RetentionSettings:
    normalized = _normalize_retention_value(payload.model_dump())
    row = db.get(AppSetting, RETENTION_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=RETENTION_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.retention.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_retention_value(row.value)


@router.get('/kindle-display', response_model=KindleDisplaySettings)
def get_kindle_display_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> KindleDisplaySettings:
    return get_kindle_display_settings_from_db(db)


@router.put('/kindle-display', response_model=KindleDisplaySettings)
def update_kindle_display_settings(
    payload: KindleDisplaySettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> KindleDisplaySettings:
    normalized = _normalize_kindle_display_value(payload.model_dump())
    row = db.get(AppSetting, KINDLE_DISPLAY_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=KINDLE_DISPLAY_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.kindle_display.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_kindle_display_value(row.value)




@router.get('/public-dashboard', response_model=PublicDashboardSettings)
def get_public_dashboard_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> PublicDashboardSettings:
    return get_public_dashboard_settings_from_db(db)


@router.put('/public-dashboard', response_model=PublicDashboardSettings)
def update_public_dashboard_settings(
    payload: PublicDashboardSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PublicDashboardSettings:
    normalized = _normalize_public_dashboard_value(payload.model_dump())
    row = db.get(AppSetting, PUBLIC_DASHBOARD_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=PUBLIC_DASHBOARD_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.public_dashboard.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_public_dashboard_value(row.value)


@router.get('/current-values-api', response_model=CurrentValuesApiSettings)
def get_current_values_api_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> CurrentValuesApiSettings:
    return get_current_values_api_settings_from_db(db)


@router.put('/current-values-api', response_model=CurrentValuesApiSettings)
def update_current_values_api_settings(
    payload: CurrentValuesApiSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CurrentValuesApiSettings:
    normalized = _normalize_current_values_api_value(payload.model_dump())
    row = db.get(AppSetting, CURRENT_VALUES_API_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=CURRENT_VALUES_API_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.current_values_api.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_current_values_api_value(row.value)




@router.get('/ortnetz', response_model=OrtnetzSettings)
def get_ortnetz_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> OrtnetzSettings:
    return get_ortnetz_settings_from_db(db)


@router.put('/ortnetz', response_model=OrtnetzSettings)
def update_ortnetz_settings(
    payload: OrtnetzSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrtnetzSettings:
    normalized = _normalize_ortnetz_value(payload.model_dump())
    if normalized.enabled and (normalized.device_id is None or normalized.latitude is None or normalized.longitude is None):
        raise HTTPException(status_code=422, detail='Device, latitude and longitude are required when Ortsnetz upload is enabled')
    row = db.get(AppSetting, ORTSNETZ_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=ORTSNETZ_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.ortnetz.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_ortnetz_value(row.value)


@router.get('/ortnetz/status', response_model=OrtnetzStatus)
def get_ortnetz_status(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrtnetzStatus:
    return get_ortnetz_status_from_db(db)


@router.get('/simulation', response_model=SimulationSettings)
def get_simulation_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> SimulationSettings:
    return get_simulation_settings_from_db(db)


@router.put('/simulation', response_model=SimulationSettings)
def update_simulation_settings(
    payload: SimulationSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SimulationSettings:
    normalized = _normalize_simulation_value(payload.model_dump())
    row = db.get(AppSetting, SIMULATION_SETTINGS_KEY)
    value = normalized.model_dump()
    if row is None:
        row = AppSetting(key=SIMULATION_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    if not normalized.enabled:
        cache_row = db.get(AppSetting, SIMULATION_CACHE_KEY)
        if cache_row is not None:
            db.delete(cache_row)
    db.add(AuditLog(actor_user_id=actor.id, action='settings.simulation.update', details=value))
    db.commit()
    db.refresh(row)
    return _normalize_simulation_value(row.value)


@router.get('/air-sensor', response_model=AirSensorSettings)
def get_air_sensor_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> AirSensorSettings:
    return get_air_sensor_settings_from_db(db)


@router.put('/air-sensor', response_model=AirSensorSettings)
def update_air_sensor_settings(
    payload: AirSensorSettings,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AirSensorSettings:
    raw_value = payload.model_dump()
    row = db.get(AppSetting, AIR_SENSOR_SETTINGS_KEY)
    existing_value = row.value if row and isinstance(row.value, dict) else {}
    raw_value['host'] = _normalize_host_or_400(raw_value.get('host'))
    raw_value['altitude_m'] = _air_sensor_altitude_m(raw_value.get('altitude_m'))
    api_key_changed = _apply_weather_underground_api_key_update(raw_value, existing_value)
    raw_value['weather_underground_station_id'] = str(raw_value.get('weather_underground_station_id') or '').strip().upper() or None
    raw_value['weather_underground_upload_url'] = str(raw_value.get('weather_underground_upload_url') or '').strip() or DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE
    normalized = _normalize_air_sensor_value(raw_value)
    value = normalized.model_dump()
    value.pop('weather_underground_api_key', None)
    value.pop('weather_underground_api_key_set', None)
    if raw_value.get('weather_underground_api_key_ciphertext'):
        value['weather_underground_api_key_ciphertext'] = raw_value.get('weather_underground_api_key_ciphertext')
    if row is None:
        row = AppSetting(key=AIR_SENSOR_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    db.add(AuditLog(actor_user_id=actor.id, action='settings.air_sensor.update', details={
        'enabled': value.get('enabled'),
        'host': value.get('host'),
        'altitude_m': value.get('altitude_m'),
        'weather_underground_enabled': value.get('weather_underground_enabled'),
        'weather_underground_station_id': value.get('weather_underground_station_id'),
        'weather_underground_upload_url': value.get('weather_underground_upload_url'),
        'weather_underground_api_key_changed': api_key_changed,
    }))
    db.commit()
    db.refresh(row)
    return _normalize_air_sensor_value(row.value)


@router.get('/air-sensor/current', response_model=AirSensorCurrent)
def get_air_sensor_current(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AirSensorCurrent:
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        return simulated_air_sensor_current(get_ui_settings_from_db(db).timezone)
    return get_cached_air_sensor_current(get_air_sensor_settings_from_db(db), db)


@router.get('/public/air-sensor/current', response_model=AirSensorCurrent)
def get_public_air_sensor_current(db: Session = Depends(get_db)) -> AirSensorCurrent:
    if not get_public_dashboard_settings_from_db(db).enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Public dashboard is disabled')
    simulation = get_simulation_settings_from_db(db)
    if simulation.enabled:
        return simulated_air_sensor_current(get_ui_settings_from_db(db).timezone)
    return get_cached_air_sensor_current(get_air_sensor_settings_from_db(db), db)
