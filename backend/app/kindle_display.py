from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from typing import Any
from io import BytesIO

import cairosvg
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import SessionLocal
from .energy_retention import GRID_ENERGY_SOURCES, SOLAR_ENERGY_SOURCES, delta_energy
from .models import AppSetting, Measurement
from .simulation import simulated_air_sensor_current, simulated_values_at

AIR_SENSOR_CACHE_KEY = 'air_sensor_cache'
UI_SETTINGS_KEY = 'ui'
FINANCE_SETTINGS_KEY = 'finance'
KINDLE_DISPLAY_SETTINGS_KEY = 'kindle_display'
SIMULATION_SETTINGS_KEY = 'simulation'
DEFAULT_CURRENCY_CODE = 'EUR'
DEFAULT_TIMEZONE = 'Europe/Berlin'
GRID_POWER_SOURCES = {'shelly_3em_gen1_total', 'shelly_rpc_em_total'}
SOLAR_POWER_SOURCES = {'shelly_rpc_switch', 'shelly_rpc_pm'}
KINDLE_OUTPUT_PATH = Path('/app/data/kindle-display.png')
KINDLE_TMP_PATH = Path('/app/data/kindle-display.tmp.png')
KINDLE_WIDTH = 600
KINDLE_HEIGHT = 800
KINDLE_GENERATE_SECOND = 10
KINDLE_RENDERER_VERSION = 'kindle-inline-v8-temp-only-left-favicon'
ICON_DIR = Path(__file__).resolve().parent / 'assets' / 'icons'
_ICON_CACHE: dict[tuple[str, int], Image.Image] = {}


@dataclass(slots=True)
class KindleValues:
    generated_at: datetime
    temperature_c: float | None = None
    humidity_percent: float | None = None
    pm10: float | None = None
    pm25: float | None = None
    home_import_w: float | None = None
    solar_w: float | None = None
    today_import_kwh: float | None = None
    today_solar_kwh: float | None = None
    kwh_price: float = 0.0
    currency_code: str = DEFAULT_CURRENCY_CODE
    last_air_success_at: datetime | None = None
    last_measurement_at: datetime | None = None
    timezone_name: str = DEFAULT_TIMEZONE
    language: str = 'de'


class KindleDisplayService:
    """Render and cache a Kindle-friendly status PNG.

    The Kindle endpoint must be fast and reliable. The image is therefore
    generated in the background and atomically replaced on disk. Requests always
    return the most recent valid PNG. Rendering is intentionally delayed within
    each minute so a Kindle cron that runs at second 0 does not fetch while the
    file is being regenerated.
    """

    def __init__(self, output_path: Path = KINDLE_OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.tmp_path = output_path.with_suffix('.tmp.png')
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.last_generated_at: datetime | None = None
        self.last_error: str | None = None
        self.last_minute_key: str | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._run(), name='kindle-display-generator')

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        # Create an initial image shortly after startup. This makes the endpoint
        # useful immediately even before the first minute boundary is reached.
        await asyncio.sleep(2)
        await self.generate_once()

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            minute_key = now.strftime('%Y-%m-%d %H:%M')
            if now.second >= KINDLE_GENERATE_SECOND and minute_key != self.last_minute_key:
                if is_kindle_display_enabled():
                    await self.generate_once()
                self.last_minute_key = minute_key
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                continue

    async def generate_once(self, *, force: bool = False) -> None:
        if not force and not is_kindle_display_enabled():
            self.last_error = None
            return
        try:
            await asyncio.to_thread(self._generate_sync)
            self.last_generated_at = datetime.now(timezone.utc)
            self.last_error = None
        except Exception as exc:  # keep the previous PNG intact
            self.last_error = str(exc)

    def _generate_sync(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with SessionLocal() as db:
            values = collect_kindle_values(db)
        render_kindle_png(values, self.tmp_path)
        self.tmp_path.replace(self.output_path)

    def meta(self) -> dict[str, Any]:
        stat = self.output_path.stat() if self.output_path.exists() else None
        enabled = is_kindle_display_enabled()
        return {
            'ok': self.output_path.exists() and enabled,
            'enabled': enabled,
            'path': str(self.output_path),
            'size_bytes': stat.st_size if stat else None,
            'last_generated_at': self.last_generated_at.isoformat() if self.last_generated_at else None,
            'last_error': self.last_error,
            'generate_second': KINDLE_GENERATE_SECOND,
            'width': KINDLE_WIDTH,
            'height': KINDLE_HEIGHT,
            'renderer_version': KINDLE_RENDERER_VERSION,
        }


def is_kindle_display_enabled() -> bool:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, KINDLE_DISPLAY_SETTINGS_KEY)
            value = row.value if row and isinstance(row.value, dict) else {}
            return bool(value.get('enabled', True))
    except Exception:
        # Fail open so a temporary database issue does not permanently disable the display.
        return True


def parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def parse_float(value: object) -> float | None:
    try:
        if value is None or value == '':
            return None
        parsed = float(str(value).replace(',', '.').strip())
        if math.isnan(parsed) or math.isinf(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None



def _simulation_enabled(db: Session) -> bool:
    row = db.get(AppSetting, SIMULATION_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    return bool(value.get('enabled', False))


def _air_cache(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, AIR_SENSOR_CACHE_KEY)
    return row.value if row and isinstance(row.value, dict) else {}


def _latest_home_import_w(db: Session) -> tuple[float | None, datetime | None]:
    row = (
        db.query(Measurement)
        .filter(Measurement.source_type.in_(GRID_POWER_SOURCES))
        .filter(Measurement.total_power_w.isnot(None))
        .order_by(Measurement.timestamp.desc())
        .first()
    )
    if row is not None:
        return row.total_power_w, row.timestamp

    fallback = (
        db.query(Measurement)
        .filter(Measurement.total_power_w.isnot(None))
        .order_by(Measurement.timestamp.desc())
        .first()
    )
    if fallback is not None:
        return fallback.total_power_w, fallback.timestamp

    # Last resort: any recent power value, useful for early test installations.
    value, ts = (
        db.query(Measurement.power_w, func.max(Measurement.timestamp))
        .filter(Measurement.power_w.isnot(None))
        .group_by(Measurement.power_w)
        .order_by(func.max(Measurement.timestamp).desc())
        .first()
        or (None, None)
    )
    return value, ts


def _ui_timezone(db: Session) -> str:
    row = db.get(AppSetting, UI_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    timezone_name = str(value.get('timezone') or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = DEFAULT_TIMEZONE
    return timezone_name


def _ui_language(db: Session) -> str:
    row = db.get(AppSetting, UI_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    language = str(value.get('language') or 'de').strip().lower()
    return language if language in {'de', 'en'} else 'de'


def _zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _latest_solar_power_w(db: Session) -> float | None:
    recent = (
        db.query(Measurement)
        .filter(Measurement.source_type.in_(SOLAR_POWER_SOURCES))
        .filter(Measurement.power_w.isnot(None))
        .order_by(Measurement.timestamp.desc())
        .limit(20)
        .all()
    )
    if not recent:
        return None

    latest_by_source: dict[str, float] = {}
    for row in recent:
        if row.source_type not in latest_by_source and row.power_w is not None:
            latest_by_source[row.source_type] = max(0.0, row.power_w)
    return sum(latest_by_source.values()) if latest_by_source else None


def _today_energy_mix(db: Session, timezone_name: str) -> tuple[float | None, float | None]:
    tz = _zoneinfo(timezone_name)
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    rows = (
        db.query(Measurement)
        .filter(Measurement.timestamp >= start_utc, Measurement.timestamp < end_utc)
        .order_by(Measurement.timestamp.asc())
        .all()
    )
    imported_wh = delta_energy(rows, 'energy_import_wh', GRID_ENERGY_SOURCES)
    solar_wh = delta_energy(rows, 'energy_import_wh', SOLAR_ENERGY_SOURCES)
    imported_kwh = imported_wh / 1000.0 if imported_wh is not None else None
    solar_kwh = solar_wh / 1000.0 if solar_wh is not None else None
    return imported_kwh, solar_kwh


def _finance_settings(db: Session) -> tuple[float, str]:
    row = db.get(AppSetting, FINANCE_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    try:
        kwh_price = float(value.get('kwh_price_eur', 0.0) or 0.0)
    except (TypeError, ValueError):
        kwh_price = 0.0
    currency_code = str(value.get('currency_code') or DEFAULT_CURRENCY_CODE).upper()
    if currency_code not in {'EUR', 'USD', 'GBP'}:
        currency_code = DEFAULT_CURRENCY_CODE
    return max(0.0, kwh_price), currency_code


def collect_kindle_values(db: Session) -> KindleValues:
    timezone_name = _ui_timezone(db)
    language = _ui_language(db)
    kwh_price, currency_code = _finance_settings(db)

    if _simulation_enabled(db):
        now = datetime.now(timezone.utc)
        sim = simulated_values_at(now, timezone_name)
        air = simulated_air_sensor_current(timezone_name)
        return KindleValues(
            generated_at=now,
            temperature_c=air.temperature_c,
            humidity_percent=air.humidity_percent,
            pm10=air.sds_p1,
            pm25=air.sds_p2,
            home_import_w=sim.grid_w,
            solar_w=sim.solar_w,
            today_import_kwh=sim.import_today_kwh,
            today_solar_kwh=sim.solar_today_kwh,
            kwh_price=kwh_price,
            currency_code=currency_code,
            last_air_success_at=air.last_success_at,
            last_measurement_at=sim.timestamp,
            timezone_name=timezone_name,
            language=language,
        )

    cache = _air_cache(db)
    home_import_w, last_measurement_at = _latest_home_import_w(db)
    solar_w = _latest_solar_power_w(db)
    today_import_kwh, today_solar_kwh = _today_energy_mix(db, timezone_name)
    return KindleValues(
        generated_at=datetime.now(timezone.utc),
        temperature_c=parse_float(cache.get('temperature_c')),
        humidity_percent=parse_float(cache.get('humidity_percent')),
        pm10=parse_float(cache.get('sds_p1')),
        pm25=parse_float(cache.get('sds_p2')),
        home_import_w=home_import_w,
        solar_w=solar_w,
        today_import_kwh=today_import_kwh,
        today_solar_kwh=today_solar_kwh,
        kwh_price=kwh_price,
        currency_code=currency_code,
        last_air_success_at=parse_dt(cache.get('last_success_at')),
        last_measurement_at=last_measurement_at,
        timezone_name=timezone_name,
        language=language,
    )


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend([
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/local/share/fonts/DejaVuSans-Bold.ttf',
        ])
    candidates.extend([
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/local/share/fonts/DejaVuSans.ttf',
    ])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fmt_decimal(value: float | None, decimals: int, suffix: str, *, zero: float | None = None) -> str:
    if value is None:
        if zero is None:
            return '—'
        value = zero
    formatted = f'{value:.{decimals}f}'.replace('.', ',')
    return f'{formatted} {suffix}'.strip()


def _fmt_int(value: float | None, suffix: str, *, zero: float = 0.0) -> str:
    if value is None:
        value = zero
    return f'{value:.0f} {suffix}'.strip()


def _fmt_power_compact(value: float | None, *, zero: float = 0.0) -> str:
    if value is None:
        value = zero
    value = float(value)
    if abs(value) >= 1000.0:
        return f"{value / 1000.0:.1f}".replace('.', ',') + ' kW'
    return f"{value:.0f}".replace('.', ',') + ' W'



def _currency_symbol(currency_code: str | None) -> str:
    return {'EUR': '€', 'USD': '$', 'GBP': '£'}.get((currency_code or DEFAULT_CURRENCY_CODE).upper(), '€')


def _fmt_money_compact(value: float | None, currency_code: str | None) -> str:
    if value is None:
        value = 0.0
    symbol = _currency_symbol(currency_code)
    amount = float(value)
    if symbol == '$':
        return f"${amount:.2f}".replace('.', ',')
    if symbol == '£':
        return f"£{amount:.2f}".replace('.', ',')
    return f"{amount:.2f}".replace('.', ',') + '€'


def _center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, fill: int = 0) -> None:
    draw.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), text, font=font, fill=fill, anchor='mm')



def _load_svg_icon(name: str, size: int) -> Image.Image | None:
    """Load bundled Lucide SVG icons from disk and rasterize them for Pillow.

    Icons are stored locally in the container; no network access is used at
    runtime. The alpha channel is preserved so the icon can be pasted cleanly
    onto the grayscale Kindle image.
    """
    key = (name, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    icon_path = ICON_DIR / f'{name}.svg'
    if not icon_path.exists():
        return None
    try:
        png_bytes = cairosvg.svg2png(
            url=str(icon_path),
            output_width=size,
            output_height=size,
            background_color='transparent',
        )
        icon = Image.open(BytesIO(png_bytes)).convert('RGBA')
        _ICON_CACHE[key] = icon
        return icon
    except Exception:
        return None


def _paste_svg_icon(img: Image.Image, name: str, x: int, y: int, size: int) -> bool:
    icon = _load_svg_icon(name, size)
    if icon is None:
        return False
    # Convert black SVG strokes to grayscale while using SVG alpha as mask.
    grayscale_icon = Image.new('L', icon.size, 0)
    alpha = icon.getchannel('A')
    img.paste(grayscale_icon, (x, y), alpha)
    return True

def _draw_thermometer(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    w = int(18 * scale)
    h = int(62 * scale)
    bulb = int(28 * scale)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=w // 2, outline=0, width=4)
    draw.ellipse((x - (bulb - w) // 2, y + h - 5, x - (bulb - w) // 2 + bulb, y + h - 5 + bulb), outline=0, width=4)
    draw.line((x + w + 14, y + 12, x + w + 28, y + 12), fill=0, width=3)
    draw.line((x + w + 14, y + 26, x + w + 28, y + 26), fill=0, width=3)
    draw.line((x + w + 14, y + 40, x + w + 28, y + 40), fill=0, width=3)


def _draw_drop(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    """Draw a simple humidity drop that renders cleanly on e-ink.

    The previous polygon shape looked angular on the Kindle. This outline uses
    a smooth top/bottom combination and avoids tiny decorative details.
    """
    # Upper point and rounded lower body. Use a few wide strokes only, because
    # Kindle screens and the Pillow rasterizer do not handle fine curves well.
    cx = x + int(30 * scale)
    top = y + int(2 * scale)
    shoulder_y = y + int(30 * scale)
    bottom_y = y + int(72 * scale)
    left = x + int(4 * scale)
    right = x + int(56 * scale)

    # Two clean sloped sides.
    draw.line((cx, top, left, shoulder_y), fill=0, width=max(3, int(4 * scale)))
    draw.line((cx, top, right, shoulder_y), fill=0, width=max(3, int(4 * scale)))

    # Rounded lower part as two arcs.
    draw.arc((left, shoulder_y - int(4 * scale), right, bottom_y), 0, 180, fill=0, width=max(3, int(4 * scale)))
    draw.arc((left, shoulder_y - int(4 * scale), right, bottom_y), 180, 360, fill=0, width=max(3, int(4 * scale)))

    # Small highlight, deliberately simple.
    draw.arc((x + int(16 * scale), y + int(42 * scale), x + int(34 * scale), y + int(62 * scale)), 80, 170, fill=0, width=max(2, int(3 * scale)))

def _draw_particles(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    dots = [(8, 16), (28, 10), (48, 20), (20, 34), (42, 40), (10, 52), (31, 58), (55, 55), (7, 72), (30, 78)]
    r = max(3, int(4 * scale))
    for dx, dy in dots:
        cx = x + int(dx * scale)
        cy = y + int(dy * scale)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)


def _draw_house(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    roof = [(x, y + int(42 * scale)), (x + int(32 * scale), y + int(8 * scale)), (x + int(64 * scale), y + int(42 * scale))]
    draw.line(roof, fill=0, width=4, joint='curve')
    draw.rectangle((x + int(10 * scale), y + int(42 * scale), x + int(54 * scale), y + int(82 * scale)), outline=0, width=4)
    px = x + int(32 * scale)
    py = y + int(54 * scale)
    draw.rounded_rectangle((px - 9, py, px + 9, py + 22), radius=5, fill=0)
    draw.line((px - 6, py - 10, px - 6, py + 4), fill=0, width=3)
    draw.line((px + 6, py - 10, px + 6, py + 4), fill=0, width=3)
    draw.line((px, py + 20, px, py + 33), fill=0, width=3)


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _draw_text_center(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.ImageFont) -> None:
    w, h = _text_size(draw, text, font)
    draw.text((x - w // 2, y - h // 2), text, font=font, fill=0)


def _draw_text_right_center(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.ImageFont) -> None:
    w, h = _text_size(draw, text, font)
    draw.text((x - w, y - h // 2), text, font=font, fill=0)


def _draw_row(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    label: str,
    value: str,
    icon: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    x1, x2 = 26, KINDLE_WIDTH - 26
    row_h = 90
    draw.rounded_rectangle((x1, y, x2, y + row_h), radius=10, outline=0, width=2)

    icon_x = x1 + 38
    icon_y = y + 12
    if icon == 'thermometer':
        if not _paste_svg_icon(img, 'thermometer', icon_x + 4, icon_y + 6, 58):
            _draw_thermometer(draw, icon_x + 18, icon_y + 1, 0.75)
    elif icon == 'droplets':
        if not _paste_svg_icon(img, 'droplets', icon_x + 4, icon_y + 8, 58):
            _draw_drop(draw, icon_x + 8, icon_y + 0, 0.68)
    elif icon == 'wind':
        if not _paste_svg_icon(img, 'wind', icon_x + 2, icon_y + 14, 62):
            _draw_particles(draw, icon_x + 6, icon_y + 1, 0.86)
    elif icon == 'house-plug':
        if not _paste_svg_icon(img, 'house-plug', icon_x + 0, icon_y + 5, 66):
            _draw_house(draw, icon_x + 5, icon_y - 1, 0.83)

    cy = y + row_h // 2
    draw.text((142, cy), label, font=fonts['label'], fill=0, anchor='lm')
    _draw_text_right_center(draw, KINDLE_WIDTH - 52, cy, value, fonts['value'])


def _draw_compact_card(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    icon: str,
    fonts: dict[str, ImageFont.ImageFont],
    short_label: str | None = None,
    *,
    inline: bool = False,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=12, outline=0, width=2)

    if inline:
        # Clearly horizontal: icon left, value+unit directly next to it.
        icon_size = 54
        # Temperatur braucht mehr Platz für °C und sitzt deshalb weiter links.
        # Luftfeuchte bleibt an der bisherigen, optisch guten Position.
        icon_x = x1 - 2 if icon == 'thermometer' else x1 + 6
        icon_y = y1 + ((y2 - y1) - icon_size) // 2
        if icon == 'thermometer':
            if not _paste_svg_icon(img, 'thermometer', icon_x, icon_y, icon_size):
                _draw_thermometer(draw, icon_x + 14, icon_y + 1, 0.8)
        elif icon == 'droplets':
            if not _paste_svg_icon(img, 'droplets', icon_x, icon_y, icon_size):
                _draw_drop(draw, icon_x + 8, icon_y + 2, 0.8)

        value_x = icon_x + icon_size + 10
        value_y = y1 + (y2 - y1) // 2 + 3
        draw.text((value_x, value_y), value, font=fonts['inline_value'], fill=0, anchor='lm')
        return

    # PM cards: icon/short label above, compact value below. Slightly smaller
    # font so long "ug/m3" values never overlap across the center gap.
    icon_size = 54
    icon_x = x1 + 18
    icon_y = y1 + 8
    if icon == 'wind':
        if not _paste_svg_icon(img, 'wind', icon_x, icon_y + 3, icon_size):
            _draw_particles(draw, icon_x + 8, icon_y + 2, 0.86)

    if short_label:
        draw.text((x1 + 22, y1 + 66), short_label, font=fonts['small_label'], fill=0, anchor='lm')

    value_y = y1 + 100
    _draw_text_center(draw, (x1 + x2) // 2, value_y, value, fonts['pm_value'])


def _draw_donut(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, width: int, percent: float) -> None:
    cx, cy = center
    # Outer ring
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=0, width=width)
    # Light solar segment in grayscale. Start at top.
    if percent > 0:
        start = -90
        end = start + int(360 * max(0.0, min(1.0, percent)))
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=start, end=end, fill=140, width=width)


def _draw_home_import_card(img: Image.Image, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], values: KindleValues, fonts: dict[str, ImageFont.ImageFont]) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18, outline=0, width=2)

    home_w = values.home_import_w if values.home_import_w is not None else 0.0
    solar_w = values.solar_w if values.solar_w is not None else 0.0

    # Donut uses the current day's accumulated energy mix.
    import_day = max(0.0, values.today_import_kwh or 0.0)
    solar_day = max(0.0, values.today_solar_kwh or 0.0)
    total_day = import_day + solar_day
    solar_pct = (solar_day / total_day * 100.0) if total_day > 0 else 0.0

    consumption_cost = import_day * max(0.0, values.kwh_price)
    savings = solar_day * max(0.0, values.kwh_price)

    draw.text((x1 + 22, y1 + 24), 'Hausbezug', font=fonts['card_title'], fill=0)

    # Large icons and two clean right-aligned value columns:
    #   [icon]          [W/kW] [cost/savings]
    icon_size = 52
    icon_x = x1 + 24
    power_right = x1 + 245
    money_right = x1 + 360
    row1_y = y1 + 106
    row2_y = y1 + 154

    if not _paste_svg_icon(img, 'transmission-tower', icon_x, row1_y - 40, icon_size):
        draw.line((icon_x + 26, row1_y - 42, icon_x + 8, row1_y + 8), fill=0, width=3)
        draw.line((icon_x + 26, row1_y - 42, icon_x + 44, row1_y + 8), fill=0, width=3)
        draw.line((icon_x + 12, row1_y - 16, icon_x + 40, row1_y - 16), fill=0, width=3)
    draw.text((power_right, row1_y), _fmt_power_compact(home_w, zero=0.0), font=fonts['home_value'], fill=0, anchor='rs')
    draw.text((money_right, row1_y), _fmt_money_compact(consumption_cost, values.currency_code), font=fonts['money_value'], fill=0, anchor='rs')

    if not _paste_svg_icon(img, 'sun', icon_x, row2_y - 40, icon_size):
        draw.ellipse((icon_x + 14, row2_y - 30, icon_x + 38, row2_y - 6), outline=0, width=3)
    draw.text((power_right, row2_y), _fmt_power_compact(solar_w, zero=0.0), font=fonts['home_value'], fill=0, anchor='rs')
    draw.text((money_right, row2_y), _fmt_money_compact(savings, values.currency_code), font=fonts['money_value'], fill=0, anchor='rs')

    dcx = x2 - 96
    dcy = y1 + 100
    _draw_donut(draw, (dcx, dcy), 58, 14, solar_pct / 100.0)
    _draw_text_center(draw, dcx, dcy - 8, f"{solar_pct:.0f} %", fonts['donut_pct'])
    _draw_text_center(draw, dcx, dcy + 18, 'Solar', fonts['donut_label'])


def _kindle_date_text(dt: datetime, language: str) -> str:
    if language == 'en':
        return dt.strftime('%m/%d/%Y')
    return dt.strftime('%d.%m.%Y')


def _kindle_time_text(dt: datetime, language: str, *, with_seconds: bool = False) -> str:
    if language == 'en':
        return dt.strftime('%I:%M:%S %p' if with_seconds else '%I:%M %p').lstrip('0')
    return dt.strftime('%H:%M:%S' if with_seconds else '%H:%M')


def _kindle_updated_label(language: str) -> str:
    return 'Updated' if language == 'en' else 'Aktualisiert'


def render_kindle_png(values: KindleValues, output_path: Path) -> None:
    img = Image.new('L', (KINDLE_WIDTH, KINDLE_HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    fonts = {
        'date': _font(32),
        'small_label': _font(20, bold=True),
        'inline_value': _font(58, bold=True),
        'pm_value': _font(34, bold=True),
        'time': _font(176, bold=True),
        'footer': _font(22),
        'card_title': _font(30),
        'home_label': _font(25, bold=True),
        'home_value': _font(36, bold=True),
        'money_value': _font(29, bold=True),
        'donut_pct': _font(28, bold=True),
        'donut_label': _font(18),
    }

    tz = _zoneinfo(values.timezone_name)
    now_local = datetime.now(tz)
    display_time = now_local + timedelta(minutes=1)

    _draw_text_center(draw, KINDLE_WIDTH // 2, 18, _kindle_date_text(display_time, values.language), fonts['date'])

    _draw_home_import_card(img, draw, (10, 46, KINDLE_WIDTH - 10, 228), values, fonts)

    left_x1, left_x2 = 12, 294
    right_x1, right_x2 = 306, KINDLE_WIDTH - 12
    top_y1, top_y2 = 242, 358
    bottom_y1, bottom_y2 = 370, 492

    _draw_compact_card(
        img, draw, (left_x1, top_y1, left_x2, top_y2),
        _fmt_decimal(values.temperature_c, 1, '°C', zero=0.0).replace(' °C', '°C'),
        'thermometer', fonts, inline=True,
    )
    _draw_compact_card(
        img, draw, (right_x1, top_y1, right_x2, top_y2),
        _fmt_decimal(values.humidity_percent, 0, '%', zero=0.0).replace(' %', '%'),
        'droplets', fonts, inline=True,
    )
    _draw_compact_card(
        img, draw, (left_x1, bottom_y1, left_x2, bottom_y2),
        _fmt_decimal(values.pm10, 1, 'ug/m3', zero=0.0),
        'wind', fonts, short_label='10',
    )
    _draw_compact_card(
        img, draw, (right_x1, bottom_y1, right_x2, bottom_y2),
        _fmt_decimal(values.pm25, 1, 'ug/m3', zero=0.0),
        'wind', fonts, short_label='2.5',
    )

    _draw_text_center(draw, KINDLE_WIDTH // 2, 650, _kindle_time_text(display_time, values.language), fonts['time'])
    _draw_text_center(draw, KINDLE_WIDTH // 2, 776, f'{_kindle_updated_label(values.language)}: {_kindle_time_text(now_local, values.language, with_seconds=True)}', fonts['footer'])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format='PNG', optimize=True)


kindle_display_service = KindleDisplayService()
