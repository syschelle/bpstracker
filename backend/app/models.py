from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceType(str, Enum):
    auto = 'auto'
    shelly_3em_gen1 = 'shelly_3em_gen1'
    shelly_pro_3em_gen2 = 'shelly_pro_3em_gen2'
    shelly_2pm_gen4 = 'shelly_2pm_gen4'
    shelly_ng_generic = 'shelly_ng_generic'


class UserRole(str, Enum):
    admin = 'admin'
    viewer = 'viewer'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.viewer, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Encrypted with Fernet via app.security; never returned through the API.
    totp_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint('role', name='uq_users_role_singleton'),
    )


class RecoveryCode(Base):
    __tablename__ = 'recovery_codes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class Device(Base):
    __tablename__ = 'devices'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    device_type: Mapped[DeviceType] = mapped_column(SAEnum(DeviceType), default=DeviceType.auto)
    host: Mapped[str] = mapped_column(String(255), index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)
    channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    measurements: Mapped[list['Measurement']] = relationship(back_populates='device', cascade='all,delete')
    status: Mapped['DeviceStatus'] = relationship(back_populates='device', uselist=False, cascade='all,delete')

    __table_args__ = (
        UniqueConstraint('host', 'name', name='uq_device_host_name'),
    )


class DeviceStatus(Base):
    __tablename__ = 'device_status'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey('devices.id', ondelete='CASCADE'), unique=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    device: Mapped[Device] = relationship(back_populates='status')


class Measurement(Base):
    __tablename__ = 'measurements'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey('devices.id', ondelete='CASCADE'), index=True)
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_import_wh: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_export_wh: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    device: Mapped[Device] = relationship(back_populates='measurements')


Index('ix_measurements_device_timestamp', Measurement.device_id, Measurement.timestamp.desc())


class DailyEnergySummary(Base):
    __tablename__ = 'daily_energy_summary'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    imported_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    exported_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    solar_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = 'audit_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AppSetting(Base):
    __tablename__ = 'app_settings'

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
