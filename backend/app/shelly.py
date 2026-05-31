from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import httpx

from .models import DeviceType
from .network_security import OutboundHostError, lan_http_url, normalize_outbound_http_host, resolve_lan_http_target


@dataclass
class ShellyCredentials:
    username: str | None = None
    password: str | None = None


@dataclass
class ShellyDeviceConfig:
    host: str
    device_type: DeviceType
    channel: int | None = None
    credentials: ShellyCredentials | None = None


@dataclass
class NormalizedMeasurement:
    timestamp: datetime
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
    raw_json: dict[str, Any] | None = None


@dataclass
class ShellyPollResult:
    detected_type: str
    generation: str
    model: str | None
    firmware: str | None
    raw: dict[str, Any]
    measurements: list[NormalizedMeasurement]


class ShellyClientError(RuntimeError):
    pass


def normalize_shelly_host(host: str | None) -> str | None:
    return normalize_outbound_http_host(host)


def detected_device_type(detected_type: str | None, generation: str | None = None) -> DeviceType | None:
    """Map a runtime Shelly detection result to a persisted configuration type.

    Runtime detection can be more specific than the user-facing DeviceType enum
    (for example ``shelly_ng_switch_pm``). Persist the closest supported enum so
    an auto-created device does not remain in the ambiguous ``auto`` mode after
    a successful detection.
    """
    value = str(detected_type or '').strip().lower()
    gen = str(generation or '').strip().lower()
    if value == DeviceType.shelly_3em_gen1.value:
        return DeviceType.shelly_3em_gen1
    if value == DeviceType.shelly_pro_3em_gen2.value:
        return DeviceType.shelly_pro_3em_gen2
    if value == DeviceType.shelly_2pm_gen4.value:
        return DeviceType.shelly_2pm_gen4
    if value == 'shelly_ng_switch_pm':
        return DeviceType.shelly_2pm_gen4 if gen in {'4', 'gen4'} else DeviceType.shelly_ng_generic
    if value == DeviceType.shelly_ng_generic.value:
        return DeviceType.shelly_ng_generic
    return None


def _auth(credentials: ShellyCredentials | None) -> httpx.Auth | None:
    if credentials and credentials.username and credentials.password:
        return httpx.DigestAuth(credentials.username, credentials.password)
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_number(obj: dict[str, Any], *keys: str) -> float | None:
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _number(current)


class ShellyClient:
    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    async def _get_json(self, host: str, path: str, credentials: ShellyCredentials | None) -> dict[str, Any]:
        try:
            target = resolve_lan_http_target(host)
            url = lan_http_url(target, path)
        except OutboundHostError as exc:
            raise ShellyClientError(f'{path} blocked for {host}: {exc}') from exc

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, auth=_auth(credentials), follow_redirects=False) as client:
                response = await client.get(url, headers={'Host': target.host_header})
                if response.is_redirect:
                    location = response.headers.get('location', '')
                    raise ShellyClientError(f'{path} redirect blocked for {host}: {location}')
                response.raise_for_status()
                data = response.json()
        except ShellyClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface device communication error to UI
            raise ShellyClientError(f'{path} failed for {host}: {exc}') from exc
        if not isinstance(data, dict):
            raise ShellyClientError(f'{path} returned non-object JSON for {host}')
        return data

    async def poll(self, config: ShellyDeviceConfig) -> ShellyPollResult:
        if config.device_type == DeviceType.shelly_3em_gen1:
            return await self.poll_gen1_3em(config)
        if config.device_type in {DeviceType.shelly_2pm_gen4, DeviceType.shelly_pro_3em_gen2, DeviceType.shelly_ng_generic}:
            return await self.poll_rpc(config)
        return await self.poll_auto(config)

    async def poll_auto(self, config: ShellyDeviceConfig) -> ShellyPollResult:
        errors: list[str] = []
        try:
            return await self.poll_rpc(config)
        except ShellyClientError as exc:
            errors.append(str(exc))
        try:
            return await self.poll_gen1_3em(config)
        except ShellyClientError as exc:
            errors.append(str(exc))
        raise ShellyClientError('Auto detection failed: ' + ' | '.join(errors))

    async def poll_gen1_3em(self, config: ShellyDeviceConfig) -> ShellyPollResult:
        credentials = config.credentials
        status = await self._get_json(config.host, '/status', credentials)
        now = datetime.now(timezone.utc)
        emeters = status.get('emeters') or []
        if not isinstance(emeters, list):
            raise ShellyClientError('Gen1 /status did not contain emeters list')

        total_power = _number(status.get('total_power'))
        measurements: list[NormalizedMeasurement] = []
        for idx, em in enumerate(emeters):
            if not isinstance(em, dict):
                continue
            measurements.append(
                NormalizedMeasurement(
                    timestamp=now,
                    source_type='shelly_3em_gen1_emeter',
                    channel=idx,
                    phase=f'L{idx + 1}',
                    power_w=_number(em.get('power')),
                    voltage_v=_number(em.get('voltage')),
                    current_a=_number(em.get('current')),
                    power_factor=_number(em.get('pf')),
                    energy_import_wh=_number(em.get('total')),
                    energy_export_wh=_number(em.get('total_returned')),
                    total_power_w=total_power,
                    raw_json=em,
                )
            )

        if total_power is not None:
            measurements.append(
                NormalizedMeasurement(
                    timestamp=now,
                    source_type='shelly_3em_gen1_total',
                    channel=None,
                    phase='total',
                    power_w=total_power,
                    total_power_w=total_power,
                    raw_json={'total_power': total_power},
                )
            )

        model = status.get('device', {}).get('type') if isinstance(status.get('device'), dict) else status.get('type')
        firmware = status.get('fw')
        if not firmware and isinstance(status.get('update'), dict):
            firmware = status['update'].get('old_version')
        return ShellyPollResult(
            detected_type='shelly_3em_gen1',
            generation='gen1',
            model=model or 'Shelly 3EM Gen1',
            firmware=firmware,
            raw={'status': status},
            measurements=measurements,
        )

    async def poll_rpc(self, config: ShellyDeviceConfig) -> ShellyPollResult:
        credentials = config.credentials
        status, info = await asyncio.gather(
            self._get_json(config.host, '/rpc/Shelly.GetStatus', credentials),
            self._get_json(config.host, '/rpc/Shelly.GetDeviceInfo', credentials),
        )
        now = datetime.now(timezone.utc)
        measurements = parse_rpc_status(status, now, config.channel)

        # Some devices expose richer endpoint-specific responses than Shelly.GetStatus.
        # These calls are optional and ignored if a method is not available.
        optional_raw: dict[str, Any] = {}
        if config.device_type in {DeviceType.shelly_2pm_gen4, DeviceType.shelly_ng_generic, DeviceType.auto}:
            ids = [config.channel] if config.channel is not None else [0, 1]
            for switch_id in ids:
                try:
                    sw = await self._get_json(config.host, f'/rpc/Switch.GetStatus?id={switch_id}', credentials)
                    optional_raw[f'switch:{switch_id}:direct'] = sw
                    measurements.extend(parse_switch_status(sw, now, switch_id))
                except ShellyClientError:
                    pass

        if config.device_type in {DeviceType.shelly_pro_3em_gen2, DeviceType.shelly_ng_generic, DeviceType.auto}:
            for method in ('EM.GetStatus', 'EMData.GetStatus'):
                try:
                    em = await self._get_json(config.host, f'/rpc/{method}?id=0', credentials)
                    optional_raw[method] = em
                    if method == 'EM.GetStatus':
                        measurements.extend(parse_em_status(em, now, channel=0))
                    else:
                        measurements.extend(parse_emdata_status(em, now, channel=0))
                except ShellyClientError:
                    pass

        model = info.get('model') or info.get('app') or 'Shelly RPC device'
        firmware = info.get('fw_id') or info.get('ver')
        gen = str(info.get('gen') or 'gen2+')
        return ShellyPollResult(
            detected_type=detect_rpc_type(info, status),
            generation=gen,
            model=model,
            firmware=firmware,
            raw={'info': info, 'status': status, **optional_raw},
            measurements=deduplicate_measurements(measurements),
        )


def detect_rpc_type(info: dict[str, Any], status: dict[str, Any]) -> str:
    model = str(info.get('model') or info.get('app') or '').lower()
    if '2pm' in model or any(key.startswith('switch:') for key in status):
        return 'shelly_2pm_gen4' if 'gen4' in model or str(info.get('gen')) == '4' else 'shelly_ng_switch_pm'
    if '3em' in model or any(key.startswith('em:') for key in status):
        return 'shelly_pro_3em_gen2'
    return 'shelly_ng_generic'


def deduplicate_measurements(measurements: list[NormalizedMeasurement]) -> list[NormalizedMeasurement]:
    seen: set[tuple[str, int | None, str | None]] = set()
    result: list[NormalizedMeasurement] = []
    # Prefer direct method measurements first by reversing twice to keep latest richer reads.
    for measurement in reversed(measurements):
        key = (measurement.source_type, measurement.channel, measurement.phase)
        if key in seen:
            continue
        seen.add(key)
        result.append(measurement)
    return list(reversed(result))


def parse_rpc_status(status: dict[str, Any], now: datetime, requested_channel: int | None = None) -> list[NormalizedMeasurement]:
    measurements: list[NormalizedMeasurement] = []
    for key, value in status.items():
        if not isinstance(value, dict):
            continue
        if key.startswith('switch:'):
            channel = int(key.split(':', 1)[1])
            if requested_channel is not None and channel != requested_channel:
                continue
            measurements.extend(parse_switch_status(value, now, channel))
        elif key.startswith('em:'):
            channel = int(key.split(':', 1)[1])
            measurements.extend(parse_em_status(value, now, channel))
        elif key.startswith('emdata:'):
            channel = int(key.split(':', 1)[1])
            measurements.extend(parse_emdata_status(value, now, channel))
        elif key.startswith('pm1:') or key.startswith('pm:'):
            channel = int(key.split(':', 1)[1])
            if requested_channel is not None and channel != requested_channel:
                continue
            measurements.append(
                NormalizedMeasurement(
                    timestamp=now,
                    source_type='shelly_rpc_pm',
                    channel=channel,
                    power_w=_number(value.get('apower') or value.get('power')),
                    voltage_v=_number(value.get('voltage')),
                    current_a=_number(value.get('current')),
                    energy_import_wh=_nested_number(value, 'aenergy', 'total') or _number(value.get('total')),
                    energy_export_wh=_nested_number(value, 'ret_aenergy', 'total'),
                    raw_json=value,
                )
            )
    return measurements


def parse_switch_status(value: dict[str, Any], now: datetime, channel: int) -> list[NormalizedMeasurement]:
    return [
        NormalizedMeasurement(
            timestamp=now,
            source_type='shelly_rpc_switch',
            channel=channel,
            phase=None,
            power_w=_number(value.get('apower') or value.get('power')),
            voltage_v=_number(value.get('voltage')),
            current_a=_number(value.get('current')),
            power_factor=_number(value.get('pf')),
            energy_import_wh=_nested_number(value, 'aenergy', 'total') or _number(value.get('total')),
            energy_export_wh=_nested_number(value, 'ret_aenergy', 'total'),
            total_power_w=_number(value.get('apower') or value.get('power')),
            raw_json=value,
        )
    ]


def parse_em_status(value: dict[str, Any], now: datetime, channel: int) -> list[NormalizedMeasurement]:
    measurements: list[NormalizedMeasurement] = []
    total_power = _number(value.get('total_act_power') or value.get('total_active_power') or value.get('total_power'))
    # Known Shelly-NG EM shapes include either a/b/c phase objects or current/voltage arrays depending on device.
    phase_keys = [('a', 'L1'), ('b', 'L2'), ('c', 'L3')]
    for key, label in phase_keys:
        phase_obj = value.get(key)
        if isinstance(phase_obj, dict):
            measurements.append(
                NormalizedMeasurement(
                    timestamp=now,
                    source_type='shelly_rpc_em',
                    channel=channel,
                    phase=label,
                    power_w=_number(phase_obj.get('active_power') or phase_obj.get('act_power')),
                    voltage_v=_number(phase_obj.get('voltage')),
                    current_a=_number(phase_obj.get('current')),
                    power_factor=_number(phase_obj.get('pf')),
                    total_power_w=total_power,
                    raw_json=phase_obj,
                )
            )

    for idx in range(3):
        current = value.get('current')
        voltage = value.get('voltage')
        active_power = value.get('act_power') or value.get('active_power')
        pf = value.get('pf')
        if isinstance(active_power, list) or isinstance(current, list) or isinstance(voltage, list):
            measurements.append(
                NormalizedMeasurement(
                    timestamp=now,
                    source_type='shelly_rpc_em',
                    channel=channel,
                    phase=f'L{idx + 1}',
                    power_w=_number(active_power[idx]) if isinstance(active_power, list) and idx < len(active_power) else None,
                    voltage_v=_number(voltage[idx]) if isinstance(voltage, list) and idx < len(voltage) else None,
                    current_a=_number(current[idx]) if isinstance(current, list) and idx < len(current) else None,
                    power_factor=_number(pf[idx]) if isinstance(pf, list) and idx < len(pf) else None,
                    total_power_w=total_power,
                    raw_json=value,
                )
            )

    if total_power is not None:
        measurements.append(
            NormalizedMeasurement(
                timestamp=now,
                source_type='shelly_rpc_em_total',
                channel=channel,
                phase='total',
                power_w=total_power,
                total_power_w=total_power,
                raw_json={'total_power': total_power},
            )
        )
    return measurements


def parse_emdata_status(value: dict[str, Any], now: datetime, channel: int) -> list[NormalizedMeasurement]:
    total_import = _number(value.get('total_act_energy') or value.get('total_energy') or value.get('total'))
    total_returned = _number(value.get('total_act_ret_energy') or value.get('total_returned') or value.get('returned'))
    return [
        NormalizedMeasurement(
            timestamp=now,
            source_type='shelly_rpc_emdata',
            channel=channel,
            phase='total',
            energy_import_wh=total_import,
            energy_export_wh=total_returned,
            raw_json=value,
        )
    ]
