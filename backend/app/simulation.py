from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from .schemas import HistoryPoint, MeasurementRead, SummaryResponse

DEFAULT_TIMEZONE = 'Europe/Berlin'
SIMULATED_PV_PEAK_W = 800.0
SIMULATED_HOUSEHOLD = '2-person household'


@dataclass(frozen=True)
class SimulatedValues:
    timestamp: datetime
    solar_w: float
    consumption_w: float
    grid_w: float
    solar_today_kwh: float
    import_today_kwh: float
    export_today_kwh: float
    solar_total_kwh: float
    import_total_kwh: float
    export_total_kwh: float


def _zoneinfo(timezone_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _day_seed(dt: datetime) -> int:
    return int(dt.strftime('%Y%m%d'))


def _noise(seed: int, scale: float = 1.0) -> float:
    rng = random.Random(seed)
    return (rng.random() * 2.0 - 1.0) * scale


def _smooth_pulse(hour: float, center: float, width: float, height: float) -> float:
    return height * math.exp(-((hour - center) ** 2) / (2 * width * width))


def solar_power_at(local_dt: datetime) -> float:
    """Realistic-ish 800 W balcony PV curve with deterministic cloud variation."""
    hour = local_dt.hour + local_dt.minute / 60 + local_dt.second / 3600
    day_of_year = local_dt.timetuple().tm_yday

    # Seasonal daylight approximation for central Europe.
    daylight_hours = 8.0 + 8.0 * max(0.0, math.sin((2 * math.pi * (day_of_year - 80)) / 365.0))
    sunrise = 12.0 - daylight_hours / 2.0
    sunset = 12.0 + daylight_hours / 2.0
    if hour < sunrise or hour > sunset:
        return 0.0

    daylight_pos = (hour - sunrise) / max(0.1, daylight_hours)
    sun_curve = math.sin(math.pi * daylight_pos)

    # Lower winter sun, stronger summer sun.
    seasonal_factor = 0.35 + 0.65 * max(0.0, math.sin((2 * math.pi * (day_of_year - 80)) / 365.0))

    seed = _day_seed(local_dt)
    base_cloud = 0.72 + _noise(seed + 13, 0.22)
    cloud_wave_1 = 0.14 * math.sin(hour * 1.7 + seed % 17)
    cloud_wave_2 = 0.09 * math.sin(hour * 4.9 + seed % 29)
    minute_flicker = _noise(seed * 1000 + local_dt.hour * 60 + local_dt.minute, 0.04)
    cloud_factor = min(1.0, max(0.18, base_cloud + cloud_wave_1 + cloud_wave_2 + minute_flicker))

    power = SIMULATED_PV_PEAK_W * sun_curve * seasonal_factor * cloud_factor

    # Small inverter threshold / low-light cut-off.
    return round(max(0.0, power if power >= 8 else 0.0), 1)


def consumption_power_at(local_dt: datetime) -> float:
    """2-person household load profile with deterministic appliance spikes."""
    hour = local_dt.hour + local_dt.minute / 60 + local_dt.second / 3600
    seed = _day_seed(local_dt)

    base = 155.0
    night = 35.0 if hour < 6.0 or hour > 23.0 else 0.0
    morning = _smooth_pulse(hour, 7.3, 0.75, 420.0)
    lunch = _smooth_pulse(hour, 12.4, 0.55, 220.0)
    evening = _smooth_pulse(hour, 19.0, 1.25, 560.0)
    tv = 100.0 if 19.5 <= hour <= 22.7 else 0.0
    fridge_cycle = 55.0 if ((local_dt.hour * 60 + local_dt.minute + seed) % 47) < 14 else 0.0

    # Deterministic occasional appliance events.
    appliance = 0.0
    minute_of_day = local_dt.hour * 60 + local_dt.minute
    for offset, height, duration in (
        ((seed * 7) % 720 + 420, 900.0, 18),   # dishwasher/washing machine around daytime/evening
        ((seed * 11) % 300 + 1080, 650.0, 12), # kettle/cooking short evening spike
    ):
        if offset <= minute_of_day <= offset + duration:
            phase = (minute_of_day - offset) / max(1, duration)
            appliance += height * math.sin(math.pi * phase)

    jitter = _noise(seed * 10000 + minute_of_day, 45.0)
    return round(max(80.0, base + night + morning + lunch + evening + tv + fridge_cycle + appliance + jitter), 1)


def simulated_values_at(utc_dt: datetime, timezone_name: str | None = DEFAULT_TIMEZONE) -> SimulatedValues:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    tz = _zoneinfo(timezone_name)
    local_dt = utc_dt.astimezone(tz)
    solar_w = solar_power_at(local_dt)
    consumption_w = consumption_power_at(local_dt)
    grid_w = round(consumption_w - solar_w, 1)

    start_local = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_elapsed = local_dt.hour * 60 + local_dt.minute

    solar_wh = 0.0
    import_wh = 0.0
    export_wh = 0.0
    step_minutes = 5
    for minute in range(0, minutes_elapsed + 1, step_minutes):
        sample_local = start_local + timedelta(minutes=minute)
        s = solar_power_at(sample_local)
        c = consumption_power_at(sample_local)
        g = c - s
        solar_wh += s * step_minutes / 60.0
        if g >= 0:
            import_wh += g * step_minutes / 60.0
        else:
            export_wh += abs(g) * step_minutes / 60.0

    # Plausible totals for a demo installation that has already been running for a while.
    day_of_year = local_dt.timetuple().tm_yday
    simulated_days = 42 + (day_of_year % 60)
    solar_total = simulated_days * 2.65 + solar_wh / 1000.0
    import_total = simulated_days * 5.75 + import_wh / 1000.0
    export_total = simulated_days * 0.55 + export_wh / 1000.0

    return SimulatedValues(
        timestamp=utc_dt.astimezone(timezone.utc),
        solar_w=solar_w,
        consumption_w=consumption_w,
        grid_w=grid_w,
        solar_today_kwh=round(solar_wh / 1000.0, 3),
        import_today_kwh=round(import_wh / 1000.0, 3),
        export_today_kwh=round(export_wh / 1000.0, 3),
        solar_total_kwh=round(solar_total, 3),
        import_total_kwh=round(import_total, 3),
        export_total_kwh=round(export_total, 3),
    )



def _purpose_of(device: Any) -> str:
    return str(getattr(device, 'purpose', None) or 'auto')


def _active_devices(devices: list[Any] | None) -> list[Any]:
    return [device for device in (devices or []) if bool(getattr(device, 'is_active', True))]


def _simulated_device_groups(devices: list[Any] | None) -> tuple[list[Any], list[Any], list[Any]]:
    active = _active_devices(devices)
    grid = [device for device in active if _purpose_of(device) == 'grid']
    solar = [device for device in active if _purpose_of(device) == 'solar']
    other = [device for device in active if _purpose_of(device) in {'consumer', 'auto'}]
    # Keep demo usable even when no devices are configured yet.
    if not active:
        return [], [], []
    return grid, solar, other


def _split_value(total: float, count: int, index: int) -> float:
    if count <= 1:
        return total
    weights = [1.0 + 0.08 * math.sin((i + 1) * 1.7) for i in range(count)]
    total_weight = sum(weights)
    return total * weights[index] / total_weight


def simulated_summary(timezone_name: str, *, kwh_price: float, investment: float, currency_code: str, devices: list[Any] | None = None) -> SummaryResponse:
    now = datetime.now(timezone.utc)
    values = simulated_values_at(now, timezone_name)
    consumption_cost_today = values.import_today_kwh * kwh_price
    savings_today = values.solar_today_kwh * kwh_price
    savings_total = values.solar_total_kwh * kwh_price

    remaining = None
    progress = None
    estimated_days = None
    estimated_date = None
    if investment > 0:
        remaining = max(0.0, investment - savings_total)
        progress = min(100.0, max(0.0, (savings_total / investment) * 100.0))
        if remaining > 0 and savings_today > 0:
            estimated_days = remaining / savings_today
            estimated_date = now + timedelta(days=estimated_days)
        elif remaining == 0:
            estimated_days = 0.0
            estimated_date = now

    active_devices = _active_devices(devices)
    configured_count = len(active_devices) if active_devices else 1

    return SummaryResponse(
        current_grid_power_w=values.grid_w,
        current_solar_power_w=values.solar_w,
        current_total_power_w=values.consumption_w,
        imported_today_kwh=values.import_today_kwh,
        exported_today_kwh=values.export_today_kwh,
        solar_today_kwh=values.solar_today_kwh,
        imported_total_kwh=values.import_total_kwh,
        exported_total_kwh=values.export_total_kwh,
        solar_total_kwh=values.solar_total_kwh,
        kwh_price_eur=kwh_price,
        investment_cost_eur=investment,
        currency_code=currency_code,
        consumption_cost_today_eur=round(consumption_cost_today, 2),
        savings_today_eur=round(savings_today, 2),
        savings_total_eur=round(savings_total, 2),
        remaining_to_breakeven_eur=remaining,
        breakeven_progress_percent=progress,
        estimated_breakeven_days=estimated_days,
        estimated_breakeven_date=estimated_date,
        last_measurement_at=values.timestamp,
        device_count=configured_count,
        online_device_count=configured_count,
        raw_retention_days=30,
    )


def simulated_latest(timezone_name: str, devices: list[Any] | None = None) -> list[MeasurementRead]:
    now = datetime.now(timezone.utc)
    values = simulated_values_at(now, timezone_name)
    active = _active_devices(devices)

    if not active:
        return [
            MeasurementRead(
                id=-1,
                timestamp=values.timestamp,
                device_id=-1,
                source_type='simulation_grid',
                channel=None,
                phase=None,
                power_w=values.grid_w,
                voltage_v=230.0,
                current_a=round(abs(values.grid_w) / 230.0, 2),
                power_factor=0.98,
                energy_import_wh=round(values.import_today_kwh * 1000, 1),
                energy_export_wh=round(values.export_today_kwh * 1000, 1),
                total_power_w=values.grid_w,
            ),
            MeasurementRead(
                id=-2,
                timestamp=values.timestamp,
                device_id=-2,
                source_type='simulation_solar',
                channel=0,
                phase=None,
                power_w=-values.solar_w,
                voltage_v=230.0,
                current_a=round(values.solar_w / 230.0, 2),
                power_factor=1.0,
                energy_import_wh=round(values.solar_today_kwh * 1000, 1),
                energy_export_wh=None,
                total_power_w=None,
            ),
        ]

    grid_devices, solar_devices, other_devices = _simulated_device_groups(active)
    rows: list[MeasurementRead] = []
    row_id = -1

    for index, device in enumerate(grid_devices):
        grid_w = _split_value(values.grid_w, len(grid_devices), index)
        rows.append(MeasurementRead(
            id=row_id,
            timestamp=values.timestamp,
            device_id=int(getattr(device, 'id', row_id)),
            source_type='simulation_grid',
            channel=getattr(device, 'channel', None),
            phase=None,
            power_w=grid_w,
            voltage_v=230.0,
            current_a=round(abs(grid_w) / 230.0, 2),
            power_factor=0.98,
            energy_import_wh=round(values.import_today_kwh * 1000, 1),
            energy_export_wh=round(values.export_today_kwh * 1000, 1),
            total_power_w=grid_w,
        ))
        row_id -= 1

    for index, device in enumerate(solar_devices):
        solar_w = _split_value(values.solar_w, len(solar_devices), index)
        # Many Shelly feed-in setups report production as negative power.
        rows.append(MeasurementRead(
            id=row_id,
            timestamp=values.timestamp,
            device_id=int(getattr(device, 'id', row_id)),
            source_type='simulation_solar',
            channel=getattr(device, 'channel', 0),
            phase=None,
            power_w=-solar_w,
            voltage_v=230.0,
            current_a=round(solar_w / 230.0, 2),
            power_factor=1.0,
            energy_import_wh=round(values.solar_today_kwh * 1000 / max(1, len(solar_devices)), 1),
            energy_export_wh=None,
            total_power_w=None,
        ))
        row_id -= 1

    for index, device in enumerate(other_devices):
        consumer_w = _split_value(max(80.0, values.consumption_w - max(0.0, values.solar_w)), len(other_devices), index)
        rows.append(MeasurementRead(
            id=row_id,
            timestamp=values.timestamp,
            device_id=int(getattr(device, 'id', row_id)),
            source_type='simulation_consumer',
            channel=getattr(device, 'channel', None),
            phase=None,
            power_w=consumer_w,
            voltage_v=230.0,
            current_a=round(abs(consumer_w) / 230.0, 2),
            power_factor=0.96,
            energy_import_wh=None,
            energy_export_wh=None,
            total_power_w=None,
        ))
        row_id -= 1

    # If only consumer/ignored devices exist, keep at least one virtual aggregate row for the dashboard.
    if not rows:
        return simulated_latest(timezone_name, None)
    return rows

def simulated_history(start: datetime, end: datetime, timezone_name: str, bucket_seconds: int) -> list[HistoryPoint]:
    points: list[HistoryPoint] = []
    cursor = start
    if cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    max_points = 2500
    step = max(bucket_seconds, int((end - start).total_seconds() / max_points) if (end - start).total_seconds() > 0 else bucket_seconds)
    while cursor <= end:
        values = simulated_values_at(cursor, timezone_name)
        points.append(HistoryPoint(
            timestamp=cursor.astimezone(timezone.utc),
            device_id=-1,
            source_type='simulation',
            power_w=values.solar_w,
            total_power_w=values.grid_w,
            solar_power_w=values.solar_w,
            grid_power_w=values.grid_w,
        ))
        cursor += timedelta(seconds=step)
    return points



def simulated_air_sensor_current(timezone_name: str | None = DEFAULT_TIMEZONE):
    """Return plausible simulated air sensor values.

    Imported lazily to avoid a hard dependency from the simulation module to the
    API schema at import time in tools/tests.
    """
    from .schemas import AirSensorCurrent

    now = datetime.now(timezone.utc)
    local_dt = now.astimezone(_zoneinfo(timezone_name))
    hour = local_dt.hour + local_dt.minute / 60.0
    seed = _day_seed(local_dt)

    temp = 20.5 + 5.5 * math.sin((2 * math.pi * (hour - 6.0)) / 24.0) + _noise(seed + local_dt.hour, 0.7)
    humidity = 53.0 - 12.0 * math.sin((2 * math.pi * (hour - 6.0)) / 24.0) + _noise(seed + local_dt.minute, 3.0)
    pm10 = 6.0 + _smooth_pulse(hour, 8.0, 1.2, 5.0) + _smooth_pulse(hour, 19.0, 1.6, 6.0) + _noise(seed + 123 + local_dt.minute, 1.1)
    pm25 = 2.2 + _smooth_pulse(hour, 8.2, 1.1, 2.2) + _smooth_pulse(hour, 19.3, 1.4, 2.6) + _noise(seed + 321 + local_dt.minute, 0.5)

    return AirSensorCurrent(
        enabled=True,
        configured=True,
        ok=True,
        cached=False,
        temperature_c=round(temp, 1),
        humidity_percent=round(max(25.0, min(85.0, humidity)), 1),
        sds_p1=round(max(0.2, pm10), 2),
        sds_p2=round(max(0.1, pm25), 2),
        age_seconds=45,
        software_version='BPSTracker Simulation',
        last_success_at=now,
    )
