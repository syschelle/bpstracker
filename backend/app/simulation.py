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
MIN_SIMULATED_PV_PEAK_W = 100.0
MAX_SIMULATED_PV_PEAK_W = 5000.0
DEFAULT_SIMULATED_DAY_BASELOAD_W = 155.0
DEFAULT_SIMULATED_NIGHT_BASELOAD_W = 90.0
MIN_SIMULATED_BASELOAD_W = 0.0
MAX_SIMULATED_BASELOAD_W = 5000.0
SIMULATED_HOUSEHOLD = '2-person household'
SIMULATED_FRIDGE_POWER_W = 70.0
SIMULATED_FRIDGE_CYCLE_MINUTES = 40
SIMULATED_FRIDGE_ON_MINUTES = 20
SIMULATED_COFFEE_CUP_POWER_W = 1500.0
SIMULATED_COFFEE_CUP_MINUTES = 4
SIMULATED_STOVE_POWER_W = 2600.0
SIMULATED_STOVE_SESSION_MINUTES = 36



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


def _normalized_pv_peak_w(pv_peak_w: float | None = None) -> float:
    try:
        value = float(pv_peak_w if pv_peak_w is not None else SIMULATED_PV_PEAK_W)
    except (TypeError, ValueError):
        value = SIMULATED_PV_PEAK_W
    return min(MAX_SIMULATED_PV_PEAK_W, max(MIN_SIMULATED_PV_PEAK_W, value))


def _normalized_baseload_w(value: float | None, default: float) -> float:
    try:
        normalized = float(value if value is not None else default)
    except (TypeError, ValueError):
        normalized = default
    return min(MAX_SIMULATED_BASELOAD_W, max(MIN_SIMULATED_BASELOAD_W, normalized))


def _simulated_baseload_w(local_dt: datetime, day_baseload_w: float | None = None, night_baseload_w: float | None = None) -> float:
    hour = local_dt.hour + local_dt.minute / 60 + local_dt.second / 3600
    if 6.0 <= hour < 23.0:
        return _normalized_baseload_w(day_baseload_w, DEFAULT_SIMULATED_DAY_BASELOAD_W)
    return _normalized_baseload_w(night_baseload_w, DEFAULT_SIMULATED_NIGHT_BASELOAD_W)


def solar_power_at(local_dt: datetime, pv_peak_w: float | None = None) -> float:
    """Realistic-ish balcony PV curve with deterministic cloud variation."""
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

    power = _normalized_pv_peak_w(pv_peak_w) * sun_curve * seasonal_factor * cloud_factor

    # Small inverter threshold / low-light cut-off.
    return round(max(0.0, power if power >= 8 else 0.0), 1)


def _coffee_cup_load_w(minute_of_day: int, start_minute: int) -> float:
    if start_minute <= minute_of_day < start_minute + SIMULATED_COFFEE_CUP_MINUTES:
        return SIMULATED_COFFEE_CUP_POWER_W
    return 0.0


def _stove_session_load_w(minute_of_day: int, start_minute: int) -> float:
    if not (start_minute <= minute_of_day < start_minute + SIMULATED_STOVE_SESSION_MINUTES):
        return 0.0
    elapsed = minute_of_day - start_minute
    session_phase = elapsed / max(1, SIMULATED_STOVE_SESSION_MINUTES - 1)
    warmup_envelope = 0.72 + 0.28 * math.sin(math.pi * session_phase)
    # Electric hobs cycle thermostatically during a cooking session. This keeps
    # 2.6 kW peaks visible without turning the full evening into a flat plateau.
    cycle_minute = elapsed % 10
    thermostat_factor = 1.0 if cycle_minute < 6 else 0.25
    return SIMULATED_STOVE_POWER_W * warmup_envelope * thermostat_factor


def consumption_power_at(
    local_dt: datetime,
    day_baseload_w: float | None = None,
    night_baseload_w: float | None = None,
) -> float:
    """2-person household load profile with configurable baseload and deterministic appliance spikes."""
    hour = local_dt.hour + local_dt.minute / 60 + local_dt.second / 3600
    seed = _day_seed(local_dt)

    base = _simulated_baseload_w(local_dt, day_baseload_w, night_baseload_w)
    morning = _smooth_pulse(hour, 7.3, 0.75, 360.0)
    lunch = _smooth_pulse(hour, 12.4, 0.55, 180.0)
    evening = _smooth_pulse(hour, 19.0, 1.25, 360.0)
    tv = 100.0 if 19.5 <= hour <= 22.7 else 0.0

    minute_of_day = local_dt.hour * 60 + local_dt.minute
    fridge_cycle = (
        SIMULATED_FRIDGE_POWER_W
        if ((minute_of_day + seed) % SIMULATED_FRIDGE_CYCLE_MINUTES) < SIMULATED_FRIDGE_ON_MINUTES
        else 0.0
    )

    # Deterministic appliance events. They remain additional peaks on top of the
    # configured day/night baseload, but are kept moderate enough for demo use.
    appliance = 0.0

    # Washing machine / dishwasher style peak, usually daytime or early evening.
    laundry_start = ((seed * 7) % 720) + 420
    if laundry_start <= minute_of_day <= laundry_start + 18:
        phase = (minute_of_day - laundry_start) / 18
        appliance += 900.0 * math.sin(math.pi * phase)

    # Coffee machine: one or two short 1.5 kW cup pulses in the morning, plus an
    # occasional afternoon cup.
    coffee_start = 7 * 60 + ((seed % 20) - 5)
    appliance += _coffee_cup_load_w(minute_of_day, coffee_start)
    if seed % 2 == 0:
        appliance += _coffee_cup_load_w(minute_of_day, coffee_start + 9)
    if seed % 3 == 0:
        appliance += _coffee_cup_load_w(minute_of_day, 15 * 60 + 10 + (seed % 11))

    # One evening cooking session with a 2.6 kW stove peak.
    stove_start = 18 * 60 + 10 + (seed % 65)
    appliance += _stove_session_load_w(minute_of_day, stove_start)

    jitter = _noise(seed * 10000 + minute_of_day, 38.0)
    consumption = base + morning + lunch + evening + tv + fridge_cycle + appliance + jitter
    return round(max(base, consumption), 1)


def simulated_values_at(
    utc_dt: datetime,
    timezone_name: str | None = DEFAULT_TIMEZONE,
    pv_peak_w: float | None = None,
    day_baseload_w: float | None = None,
    night_baseload_w: float | None = None,
) -> SimulatedValues:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    tz = _zoneinfo(timezone_name)
    local_dt = utc_dt.astimezone(tz)
    solar_w = solar_power_at(local_dt, pv_peak_w)
    consumption_w = consumption_power_at(local_dt, day_baseload_w, night_baseload_w)
    grid_w = round(consumption_w - solar_w, 1)

    start_local = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_elapsed = local_dt.hour * 60 + local_dt.minute

    solar_wh = 0.0
    import_wh = 0.0
    export_wh = 0.0
    step_minutes = 5
    for minute in range(0, minutes_elapsed + 1, step_minutes):
        sample_local = start_local + timedelta(minutes=minute)
        s = solar_power_at(sample_local, pv_peak_w)
        c = consumption_power_at(sample_local, day_baseload_w, night_baseload_w)
        g = c - s
        solar_wh += s * step_minutes / 60.0
        if g >= 0:
            import_wh += g * step_minutes / 60.0
        else:
            export_wh += abs(g) * step_minutes / 60.0

    # Plausible totals for a demo installation that has already been running for a while.
    day_of_year = local_dt.timetuple().tm_yday
    simulated_days = 42 + (day_of_year % 60)
    pv_scale = _normalized_pv_peak_w(pv_peak_w) / SIMULATED_PV_PEAK_W
    day_base = _normalized_baseload_w(day_baseload_w, DEFAULT_SIMULATED_DAY_BASELOAD_W)
    night_base = _normalized_baseload_w(night_baseload_w, DEFAULT_SIMULATED_NIGHT_BASELOAD_W)
    default_weighted_base = (DEFAULT_SIMULATED_DAY_BASELOAD_W * 17.0 + DEFAULT_SIMULATED_NIGHT_BASELOAD_W * 7.0) / 24.0
    weighted_base = (day_base * 17.0 + night_base * 7.0) / 24.0
    baseload_scale = weighted_base / max(1.0, default_weighted_base)
    solar_total = simulated_days * (2.65 * pv_scale) + solar_wh / 1000.0
    import_total = simulated_days * max(1.0, (6.15 * baseload_scale) - 1.1 * (pv_scale - 1.0)) + import_wh / 1000.0
    export_total = simulated_days * max(0.05, 0.55 * pv_scale / max(0.25, baseload_scale)) + export_wh / 1000.0

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



def _enum_value(value: Any) -> str:
    return str(getattr(value, 'value', value) or '')


def _purpose_of(device: Any) -> str:
    return _enum_value(getattr(device, 'purpose', None) or 'auto')


def _device_type_of(device: Any) -> str:
    return _enum_value(getattr(device, 'device_type', None) or 'auto')


def _is_three_phase_grid_device(device: Any) -> bool:
    return _device_type_of(device) in {'auto', 'shelly_3em_gen1', 'shelly_pro_3em_gen2'}


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


def _three_phase_grid_values(total_power_w: float) -> list[tuple[int, str, float, float]]:
    # Keep the simulated 3EM close to real Shelly 3EM rows: three phase rows
    # plus a separate total row. The deterministic skew makes the phases look
    # realistic while preserving the exact aggregate power.
    base_voltages = [230.7, 229.9, 229.6]
    weights = [0.18, 0.16, 0.66]
    phase_powers = [round(total_power_w * weight, 1) for weight in weights]
    phase_powers[-1] = round(total_power_w - sum(phase_powers[:-1]), 1)
    return [
        (index, f'L{index + 1}', phase_powers[index], base_voltages[index])
        for index in range(3)
    ]


def _append_simulated_3em_rows(
    rows: list[MeasurementRead],
    *,
    row_id: int,
    device: Any,
    values: SimulatedValues,
    grid_w: float,
) -> int:
    configured_channel = getattr(device, 'channel', None)
    phase_rows = _three_phase_grid_values(grid_w)
    for channel, phase, power_w, voltage_v in phase_rows:
        if configured_channel is not None and channel != configured_channel:
            continue
        rows.append(MeasurementRead(
            id=row_id,
            timestamp=values.timestamp,
            device_id=int(getattr(device, 'id', row_id)),
            source_type='shelly_3em_gen1_emeter',
            channel=channel,
            phase=phase,
            power_w=power_w,
            voltage_v=voltage_v,
            current_a=round(abs(power_w) / voltage_v, 2),
            power_factor=0.98,
            energy_import_wh=round(values.import_today_kwh * 1000 / 3.0, 1),
            energy_export_wh=round(values.export_today_kwh * 1000 / 3.0, 1),
            total_power_w=grid_w,
        ))
        row_id -= 1

    if configured_channel is None:
        aggregate_power_w = sum(power_w for _channel, _phase, power_w, _voltage_v in phase_rows)
        rows.append(MeasurementRead(
            id=row_id,
            timestamp=values.timestamp,
            device_id=int(getattr(device, 'id', row_id)),
            source_type='shelly_3em_gen1_total',
            channel=None,
            phase='total',
            power_w=aggregate_power_w,
            voltage_v=None,
            current_a=None,
            power_factor=None,
            energy_import_wh=None,
            energy_export_wh=None,
            total_power_w=aggregate_power_w,
        ))
        row_id -= 1

    return row_id


def simulated_summary(
    timezone_name: str,
    *,
    kwh_price: float,
    investment: float,
    currency_code: str,
    devices: list[Any] | None = None,
    pv_peak_w: float | None = None,
    day_baseload_w: float | None = None,
    night_baseload_w: float | None = None,
) -> SummaryResponse:
    now = datetime.now(timezone.utc)
    values = simulated_values_at(now, timezone_name, pv_peak_w, day_baseload_w, night_baseload_w)
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


def simulated_latest(
    timezone_name: str,
    devices: list[Any] | None = None,
    pv_peak_w: float | None = None,
    day_baseload_w: float | None = None,
    night_baseload_w: float | None = None,
) -> list[MeasurementRead]:
    now = datetime.now(timezone.utc)
    values = simulated_values_at(now, timezone_name, pv_peak_w, day_baseload_w, night_baseload_w)
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
        if _is_three_phase_grid_device(device):
            row_id = _append_simulated_3em_rows(rows, row_id=row_id, device=device, values=values, grid_w=grid_w)
            continue
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
        return simulated_latest(timezone_name, None, pv_peak_w, day_baseload_w, night_baseload_w)
    return rows

def simulated_history(
    start: datetime,
    end: datetime,
    timezone_name: str,
    bucket_seconds: int,
    pv_peak_w: float | None = None,
    day_baseload_w: float | None = None,
    night_baseload_w: float | None = None,
) -> list[HistoryPoint]:
    points: list[HistoryPoint] = []
    cursor = start
    if cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    max_points = 2500
    step = max(bucket_seconds, int((end - start).total_seconds() / max_points) if (end - start).total_seconds() > 0 else bucket_seconds)
    while cursor <= end:
        values = simulated_values_at(cursor, timezone_name, pv_peak_w, day_baseload_w, night_baseload_w)
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
