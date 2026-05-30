from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import DeviceType, UserRole


class TokenResponse(BaseModel):
    access_token: str | None = None
    token_type: str = 'bearer'
    requires_2fa: bool = False
    challenge_token: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str


class TwoFaVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=32)


class TwoFaEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    is_active: bool
    totp_enabled: bool
    created_at: datetime


class TwoFaEnableResponse(UserRead):
    recovery_codes: list[str] = Field(default_factory=list)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class UserCredentialUpdate(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str | None = Field(default=None, min_length=8, max_length=256)


class DeviceBase(BaseModel):
    name: str
    device_type: DeviceType = DeviceType.auto
    host: str
    username: str | None = None
    is_active: bool = True
    poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    channel: int | None = Field(default=None, ge=0, le=8)


class DeviceCreate(DeviceBase):
    password: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    device_type: DeviceType | None = None
    host: str | None = None
    username: str | None = None
    password: str | None = None
    clear_password: bool = False
    is_active: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    channel: int | None = Field(default=None, ge=0, le=8)


class DeviceStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    online: bool
    detected_model: str | None = None
    generation: str | None = None
    firmware: str | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    raw_info: dict[str, Any] | None = None


class DeviceRead(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    status: DeviceStatusRead | None = None


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class FinanceSettings(BaseModel):
    kwh_price_eur: float = Field(default=0.30, ge=0, le=10)
    investment_cost_eur: float = Field(default=0.0, ge=0, le=1_000_000)
    currency_code: str = Field(default='EUR', pattern=r'^(EUR|USD|GBP)$')


class UiSettings(BaseModel):
    language: str = Field(default='de', pattern=r'^(de|en)$')
    timezone: str = Field(default='Europe/Berlin', max_length=64)


class RetentionSettings(BaseModel):
    raw_retention_days: int = Field(default=30, ge=7, le=3650)
    daily_aggregates_forever: bool = True


class KindleDisplaySettings(BaseModel):
    enabled: bool = True


class CurrentValuesApiSettings(BaseModel):
    enabled: bool = False




class AirSensorSettings(BaseModel):
    enabled: bool = False
    host: str | None = Field(default=None, max_length=255)


class AirSensorCurrent(BaseModel):
    enabled: bool = False
    configured: bool = False
    ok: bool = False
    cached: bool = False
    temperature_c: float | None = None
    humidity_percent: float | None = None
    sds_p1: float | None = None
    sds_p2: float | None = None
    age_seconds: int | None = None
    software_version: str | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None


class TestDeviceResponse(BaseModel):
    ok: bool
    detected_type: str | None = None
    generation: str | None = None
    model: str | None = None
    message: str
    raw: dict[str, Any] | None = None


class SummaryResponse(BaseModel):
    current_grid_power_w: float | None = None
    current_solar_power_w: float | None = None
    current_total_power_w: float | None = None
    imported_today_kwh: float | None = None
    exported_today_kwh: float | None = None
    solar_today_kwh: float | None = None
    imported_total_kwh: float | None = None
    exported_total_kwh: float | None = None
    solar_total_kwh: float | None = None
    kwh_price_eur: float = 0.0
    investment_cost_eur: float = 0.0
    currency_code: str = 'EUR'
    consumption_cost_today_eur: float | None = None
    savings_today_eur: float | None = None
    savings_total_eur: float | None = None
    remaining_to_breakeven_eur: float | None = None
    breakeven_progress_percent: float | None = None
    estimated_breakeven_days: float | None = None
    estimated_breakeven_date: datetime | None = None
    last_measurement_at: datetime | None = None
    device_count: int
    online_device_count: int
    raw_retention_days: int = 30


class HistoryPoint(BaseModel):
    timestamp: datetime
    device_id: int = 0
    source_type: str = 'aggregate_power'
    channel: int | None = None
    phase: str | None = None
    power_w: float | None = None
    total_power_w: float | None = None
    solar_power_w: float | None = None
    grid_power_w: float | None = None
