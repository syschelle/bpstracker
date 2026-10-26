from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import AppSetting, Device, DeviceStatus, Measurement
from .schemas import NotificationSettings
from .security import decrypt_secret

logger = logging.getLogger(__name__)

NOTIFICATION_SETTINGS_KEY = 'notifications'
NOTIFICATION_STATE_KEY = 'notification_state'
DEFAULT_TIMEZONE = 'Europe/Berlin'


def normalize_notification_settings(value: dict | None) -> NotificationSettings:
    value = value or {}
    provider = str(value.get('provider') or 'pushover').lower()
    if provider not in {'pushover', 'gotify'}:
        provider = 'pushover'
    report_time = str(value.get('daily_report_time') or '23:55')
    if len(report_time) != 5 or report_time[2] != ':' or not report_time.replace(':', '').isdigit():
        report_time = '23:55'
    else:
        hour, minute = map(int, report_time.split(':'))
        if hour > 23 or minute > 59:
            report_time = '23:55'
    return NotificationSettings(
        enabled=bool(value.get('enabled', False)),
        provider=provider,
        system_alerts_enabled=bool(value.get('system_alerts_enabled', True)),
        stale_minutes=max(2, min(1440, int(value.get('stale_minutes') or 10))),
        recovery_notifications=bool(value.get('recovery_notifications', True)),
        daily_report_enabled=bool(value.get('daily_report_enabled', False)),
        daily_report_time=report_time,
        pushover_user_key_set=bool(value.get('pushover_user_key_ciphertext')),
        pushover_api_token_set=bool(value.get('pushover_api_token_ciphertext')),
        gotify_url=str(value.get('gotify_url') or '').strip() or None,
        gotify_token_set=bool(value.get('gotify_token_ciphertext')),
    )


def get_notification_settings_from_db(db: Session) -> NotificationSettings:
    row = db.get(AppSetting, NOTIFICATION_SETTINGS_KEY)
    return normalize_notification_settings(row.value if row else None)


def _raw_settings(db: Session) -> dict:
    row = db.get(AppSetting, NOTIFICATION_SETTINGS_KEY)
    return dict(row.value) if row and isinstance(row.value, dict) else {}


def _timezone(db: Session) -> ZoneInfo:
    row = db.get(AppSetting, 'ui')
    name = str((row.value if row and isinstance(row.value, dict) else {}).get('timezone') or DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


async def send_notification(db: Session, title: str, message: str, *, priority: int = 0) -> None:
    settings = get_notification_settings_from_db(db)
    raw = _raw_settings(db)
    if not settings.enabled:
        raise RuntimeError('Notifications are disabled')
    timeout = httpx.Timeout(10.0)
    headers = {'User-Agent': 'BPSTracker'}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
        if settings.provider == 'pushover':
            user_key = decrypt_secret(raw.get('pushover_user_key_ciphertext'))
            api_token = decrypt_secret(raw.get('pushover_api_token_ciphertext'))
            if not user_key or not api_token:
                raise RuntimeError('Pushover user key and API token are required')
            response = await client.post(
                'https://api.pushover.net/1/messages.json',
                data={'token': api_token, 'user': user_key, 'title': title[:250], 'message': message[:1024], 'priority': priority},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get('status') != 1:
                raise RuntimeError('Pushover rejected the notification')
            return

        gotify_url = str(settings.gotify_url or '').rstrip('/')
        token = decrypt_secret(raw.get('gotify_token_ciphertext'))
        parsed = urlparse(gotify_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise RuntimeError('A valid Gotify http(s) URL is required')
        if not token:
            raise RuntimeError('Gotify application token is required')
        response = await client.post(
            f'{gotify_url}/message',
            headers={'X-Gotify-Key': token},
            json={'title': title, 'message': message, 'priority': 8 if priority > 0 else 4},
        )
        response.raise_for_status()


class NotificationMonitor:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._started_at = datetime.now(timezone.utc)
        self._unhealthy = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._started_at = datetime.now(timezone.utc)
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception('Notification monitor iteration failed')
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> None:
        with SessionLocal() as db:
            settings = get_notification_settings_from_db(db)
            if not settings.enabled:
                self._unhealthy = False
                return
            if settings.system_alerts_enabled:
                await self._check_system(db, settings)
            if settings.daily_report_enabled:
                await self._check_daily_report(db, settings)

    async def _check_system(self, db: Session, settings: NotificationSettings) -> None:
        now = datetime.now(timezone.utc)
        active_ids = [row[0] for row in db.query(Device.id).filter(Device.is_active.is_(True)).all()]
        if not active_ids:
            return
        last_measurement = db.query(func.max(Measurement.timestamp)).filter(Measurement.device_id.in_(active_ids)).scalar()
        cutoff = now - timedelta(minutes=settings.stale_minutes)
        stale = last_measurement is None or last_measurement < cutoff
        online_count = db.query(DeviceStatus).join(Device, DeviceStatus.device_id == Device.id).filter(Device.is_active.is_(True), DeviceStatus.online.is_(True)).count()
        unhealthy = stale or online_count == 0
        # Give a fresh backend enough time to collect the first measurement.
        if last_measurement is None and now - self._started_at < timedelta(minutes=settings.stale_minutes):
            unhealthy = False

        if unhealthy and not self._unhealthy:
            age_text = 'keine Messung vorhanden' if last_measurement is None else f'letzte Messung vor {max(0, int((now - last_measurement).total_seconds() // 60))} Minuten'
            await send_notification(db, 'BPSTracker Warnung', f'Die Messwerterfassung steht oder liefert keine aktuellen Daten ({age_text}). Online-Geräte: {online_count}/{len(active_ids)}.', priority=1)
            self._unhealthy = True
        elif not unhealthy and self._unhealthy:
            self._unhealthy = False
            if settings.recovery_notifications:
                await send_notification(db, 'BPSTracker wieder verfügbar', f'Die Messwerterfassung läuft wieder. Online-Geräte: {online_count}/{len(active_ids)}.')

    async def _check_daily_report(self, db: Session, settings: NotificationSettings) -> None:
        tz = _timezone(db)
        local_now = datetime.now(timezone.utc).astimezone(tz)
        hh, mm = map(int, settings.daily_report_time.split(':'))
        scheduled = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if local_now < scheduled:
            return
        state = db.get(AppSetting, NOTIFICATION_STATE_KEY)
        value = dict(state.value) if state and isinstance(state.value, dict) else {}
        today_key = local_now.date().isoformat()
        if value.get('last_daily_report_date') == today_key:
            return

        from .routers.measurements import summary  # local import avoids router/service import cycle
        result = summary(None, db)
        imported = result.imported_today_kwh or 0.0
        produced = result.solar_today_kwh or 0.0
        exported = result.exported_today_kwh or 0.0
        self_used = max(0.0, produced - exported)
        message = (
            f'Tagesbericht {local_now.strftime("%d.%m.%Y")} bis {local_now.strftime("%H:%M")}\n'
            f'Erzeugung: {produced:.2f} kWh\n'
            f'Netzbezug: {imported:.2f} kWh\n'
            f'Einspeisung: {exported:.2f} kWh\n'
            f'Eigenverbrauch PV: {self_used:.2f} kWh'
        )
        await send_notification(db, 'BPSTracker Tagesbericht', message)
        value['last_daily_report_date'] = today_key
        value['last_daily_report_at'] = datetime.now(timezone.utc).isoformat()
        if state is None:
            state = AppSetting(key=NOTIFICATION_STATE_KEY, value=value)
            db.add(state)
        else:
            state.value = value
        db.commit()


notification_monitor = NotificationMonitor()
