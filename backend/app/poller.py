from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .models import Device, DeviceStatus, DeviceType, Measurement, utcnow
from .energy_retention import cleanup_old_raw_measurements, ensure_completed_daily_summaries
from .routers.settings import get_raw_retention_hours_override, get_retention_settings_from_db
from .security import decrypt_secret
from .shelly import ShellyClient, ShellyCredentials, ShellyDeviceConfig, ShellyClientError, detected_device_type


class Poller:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = ShellyClient(timeout_seconds=settings.shelly_timeout_seconds)
        self.loop_seconds = settings.polling_loop_seconds
        self.semaphore = asyncio.Semaphore(settings.shelly_max_concurrency)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_poll: dict[int, datetime] = {}
        self._last_maintenance: datetime | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.loop_seconds)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> None:
        with SessionLocal() as db:
            devices = db.query(Device).filter(Device.is_active.is_(True)).all()
        now = datetime.now(timezone.utc)
        due = []
        for device in devices:
            last = self._last_poll.get(device.id)
            if last is None or now - last >= timedelta(seconds=device.poll_interval_seconds):
                due.append(device.id)
        if due:
            await asyncio.gather(*(self.poll_device_id(device_id) for device_id in due))
        await self.run_maintenance_if_due()


    async def run_maintenance_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_maintenance is not None and now - self._last_maintenance < timedelta(hours=1):
            return
        self._last_maintenance = now
        with SessionLocal() as db:
            try:
                retention = get_retention_settings_from_db(db)
                ensure_completed_daily_summaries(db, now)
                cleanup_old_raw_measurements(
                    db,
                    retention.raw_retention_days,
                    now,
                    raw_retention_hours=get_raw_retention_hours_override(),
                )
            except Exception:  # noqa: BLE001
                db.rollback()

    async def poll_device_id(self, device_id: int) -> None:
        async with self.semaphore:
            with SessionLocal() as db:
                device = db.get(Device, device_id)
                if not device or not device.is_active:
                    return
                self._last_poll[device.id] = datetime.now(timezone.utc)
                await poll_and_store_device(db, device, self.client)


async def poll_and_store_device(db: Session, device: Device, client: ShellyClient | None = None) -> None:
    client = client or ShellyClient(timeout_seconds=get_settings().shelly_timeout_seconds)
    credentials = ShellyCredentials(username=device.username, password=decrypt_secret(device.password_ciphertext))
    config = ShellyDeviceConfig(
        host=device.host,
        device_type=device.device_type,
        channel=device.channel,
        credentials=credentials,
    )
    status = get_or_create_status(db, device.id)
    try:
        result = await client.poll(config)
        if device.device_type == DeviceType.auto:
            persisted_type = detected_device_type(result.detected_type, result.generation)
            if persisted_type is not None and persisted_type != DeviceType.auto:
                device.device_type = persisted_type
        for measurement in result.measurements:
            db.add(
                Measurement(
                    timestamp=measurement.timestamp,
                    device_id=device.id,
                    source_type=measurement.source_type,
                    channel=measurement.channel,
                    phase=measurement.phase,
                    power_w=_round_power_w(measurement.power_w),
                    voltage_v=measurement.voltage_v,
                    current_a=measurement.current_a,
                    power_factor=measurement.power_factor,
                    energy_import_wh=measurement.energy_import_wh,
                    energy_export_wh=measurement.energy_export_wh,
                    total_power_w=_round_power_w(measurement.total_power_w),
                    raw_json=measurement.raw_json,
                )
            )
        status.online = True
        status.detected_model = result.model
        status.generation = result.generation
        status.firmware = result.firmware
        status.last_success_at = utcnow()
        status.last_error = None
        status.raw_info = {'detected_type': result.detected_type}
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        status = get_or_create_status(db, device.id)
        status.online = False
        status.last_error_at = utcnow()
        status.last_error = str(exc)
        db.commit()


def _round_power_w(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def get_or_create_status(db: Session, device_id: int) -> DeviceStatus:
    status = db.query(DeviceStatus).filter(DeviceStatus.device_id == device_id).one_or_none()
    if status:
        return status
    status = DeviceStatus(device_id=device_id)
    db.add(status)
    db.flush()
    return status
