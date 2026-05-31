from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import User, UserRole
from .poller import Poller
from .kindle_display import kindle_display_service
from .routers import auth, backups, current_values, devices, install, kindle, maintenance, measurements, settings as settings_router, users
from .security import delete_recovery_codes

poller = Poller()


def _table_names() -> set[str]:
    return set(inspect(engine).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return set()
    return {col['name'] for col in inspector.get_columns(table_name)}


def _add_column_if_missing(conn, table_name: str, columns: set[str], column_name: str, ddl: str) -> None:
    if column_name not in columns:
        conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}'))
        columns.add(column_name)


def _drop_not_null_if_column_exists(conn, table_name: str, columns: set[str], column_name: str) -> None:
    """Relax legacy columns that are no longer mapped by SQLAlchemy.

    Early BPSTracker builds had mandatory e-mail/full-name fields. Later builds
    intentionally use username-only authentication. PostgreSQL keeps old NOT
    NULL constraints, so new admin/viewer inserts can fail even though the new
    model does not know these columns anymore.
    """
    if column_name in columns:
        conn.execute(text(f'ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP NOT NULL'))


def migrate_existing_schema() -> None:
    """Best-effort migrations for BPSTracker MVP deployments.

    Early BPSTracker builds were shipped without Alembic migrations. SQLAlchemy's
    create_all() creates missing tables, but it does not add columns to tables
    that already exist. On an upgraded installation this can make the backend
    crash during startup, which appears in the browser as nginx 502 Bad Gateway.

    These migrations are intentionally conservative: they add missing nullable or
    defaulted columns and normalize legacy user fields, but they do not drop data.
    """
    tables = _table_names()
    with engine.begin() as conn:
        if 'users' in tables:
            cols = _columns('users')
            # Relax columns from the initial e-mail based prototype. They are no
            # longer written by the current username-only User model, but an old
            # database may still require them and crash the backend on insert.
            _drop_not_null_if_column_exists(conn, 'users', cols, 'email')
            _drop_not_null_if_column_exists(conn, 'users', cols, 'full_name')
            _add_column_if_missing(conn, 'users', cols, 'username', 'VARCHAR(80)')
            _add_column_if_missing(conn, 'users', cols, 'password_hash', 'VARCHAR(255)')
            _add_column_if_missing(conn, 'users', cols, 'role', "VARCHAR(20) DEFAULT 'viewer'")
            _add_column_if_missing(conn, 'users', cols, 'is_active', 'BOOLEAN DEFAULT TRUE')
            _add_column_if_missing(conn, 'users', cols, 'totp_secret', 'VARCHAR(512)')
            _add_column_if_missing(conn, 'users', cols, 'totp_enabled', 'BOOLEAN DEFAULT FALSE')
            _add_column_if_missing(conn, 'users', cols, 'created_at', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')
            _add_column_if_missing(conn, 'users', cols, 'updated_at', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')

            if 'email' in cols:
                conn.execute(text("UPDATE users SET username = lower(split_part(email, '@', 1)) WHERE username IS NULL OR username = ''"))
            conn.execute(text("UPDATE users SET username = concat('user', id) WHERE username IS NULL OR username = ''"))
            # role may be a PostgreSQL enum in upgraded databases; compare via role::text to avoid invalid enum literal casts.
            conn.execute(text("UPDATE users SET role = 'viewer' WHERE role IS NULL OR role::text = ''"))
            conn.execute(text("UPDATE users SET is_active = TRUE WHERE is_active IS NULL"))
            conn.execute(text("UPDATE users SET totp_enabled = FALSE WHERE totp_enabled IS NULL"))
            conn.execute(text("UPDATE users SET created_at = now() WHERE created_at IS NULL"))
            conn.execute(text("UPDATE users SET updated_at = now() WHERE updated_at IS NULL"))
            conn.execute(text("""
                WITH ranked AS (
                    SELECT id, username, row_number() OVER (PARTITION BY username ORDER BY id) AS rn
                    FROM users
                )
                UPDATE users u
                SET username = concat(u.username, '_', u.id)
                FROM ranked r
                WHERE u.id = r.id AND r.rn > 1
            """))
            conn.execute(text("""
                UPDATE users
                SET role = 'admin'
                WHERE id = (SELECT id FROM users ORDER BY id LIMIT 1)
                  AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin')
            """))
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username)'))

        if 'devices' in tables:
            cols = _columns('devices')
            _add_column_if_missing(conn, 'devices', cols, 'name', 'VARCHAR(120)')
            _add_column_if_missing(conn, 'devices', cols, 'device_type', "VARCHAR(50) DEFAULT 'auto'")
            _add_column_if_missing(conn, 'devices', cols, 'purpose', "VARCHAR(30) DEFAULT 'auto'")
            _add_column_if_missing(conn, 'devices', cols, 'host', 'VARCHAR(255)')
            _add_column_if_missing(conn, 'devices', cols, 'username', 'VARCHAR(255)')
            _add_column_if_missing(conn, 'devices', cols, 'password_ciphertext', 'TEXT')
            _add_column_if_missing(conn, 'devices', cols, 'is_active', 'BOOLEAN DEFAULT TRUE')
            _add_column_if_missing(conn, 'devices', cols, 'poll_interval_seconds', 'INTEGER DEFAULT 30')
            _add_column_if_missing(conn, 'devices', cols, 'channel', 'INTEGER')
            _add_column_if_missing(conn, 'devices', cols, 'created_at', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')
            _add_column_if_missing(conn, 'devices', cols, 'updated_at', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')

            if 'ip_address' in cols:
                conn.execute(text("UPDATE devices SET host = ip_address WHERE (host IS NULL OR host = '') AND ip_address IS NOT NULL"))
            conn.execute(text("UPDATE devices SET name = concat('Shelly ', id) WHERE name IS NULL OR name = ''"))
            conn.execute(text("UPDATE devices SET device_type = 'auto' WHERE device_type IS NULL OR device_type::text = ''"))
            conn.execute(text("UPDATE devices SET purpose = 'auto' WHERE purpose IS NULL OR purpose = ''"))
            conn.execute(text("UPDATE devices SET is_active = TRUE WHERE is_active IS NULL"))
            conn.execute(text("UPDATE devices SET poll_interval_seconds = 30 WHERE poll_interval_seconds IS NULL"))
            conn.execute(text("UPDATE devices SET created_at = now() WHERE created_at IS NULL"))
            conn.execute(text("UPDATE devices SET updated_at = now() WHERE updated_at IS NULL"))

        if 'device_status' in tables:
            cols = _columns('device_status')
            _add_column_if_missing(conn, 'device_status', cols, 'device_id', 'INTEGER')
            _add_column_if_missing(conn, 'device_status', cols, 'online', 'BOOLEAN DEFAULT FALSE')
            _add_column_if_missing(conn, 'device_status', cols, 'detected_model', 'VARCHAR(255)')
            _add_column_if_missing(conn, 'device_status', cols, 'generation', 'VARCHAR(50)')
            _add_column_if_missing(conn, 'device_status', cols, 'firmware', 'VARCHAR(255)')
            _add_column_if_missing(conn, 'device_status', cols, 'last_success_at', 'TIMESTAMP WITH TIME ZONE')
            _add_column_if_missing(conn, 'device_status', cols, 'last_error_at', 'TIMESTAMP WITH TIME ZONE')
            _add_column_if_missing(conn, 'device_status', cols, 'last_error', 'TEXT')
            _add_column_if_missing(conn, 'device_status', cols, 'raw_info', 'JSON')
            conn.execute(text("UPDATE device_status SET online = FALSE WHERE online IS NULL"))

        if 'measurements' in tables:
            cols = _columns('measurements')
            _add_column_if_missing(conn, 'measurements', cols, 'timestamp', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')
            _add_column_if_missing(conn, 'measurements', cols, 'device_id', 'INTEGER')
            _add_column_if_missing(conn, 'measurements', cols, 'source_type', "VARCHAR(80) DEFAULT 'unknown'")
            _add_column_if_missing(conn, 'measurements', cols, 'channel', 'INTEGER')
            _add_column_if_missing(conn, 'measurements', cols, 'phase', 'VARCHAR(20)')
            _add_column_if_missing(conn, 'measurements', cols, 'power_w', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'voltage_v', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'current_a', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'power_factor', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'energy_import_wh', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'energy_export_wh', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'total_power_w', 'DOUBLE PRECISION')
            _add_column_if_missing(conn, 'measurements', cols, 'raw_json', 'JSON')
            conn.execute(text("UPDATE measurements SET timestamp = now() WHERE timestamp IS NULL"))
            conn.execute(text("UPDATE measurements SET source_type = 'unknown' WHERE source_type IS NULL OR source_type = ''"))

        if 'audit_log' in tables:
            cols = _columns('audit_log')
            _add_column_if_missing(conn, 'audit_log', cols, 'timestamp', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')
            _add_column_if_missing(conn, 'audit_log', cols, 'actor_user_id', 'INTEGER')
            _add_column_if_missing(conn, 'audit_log', cols, 'action', 'VARCHAR(120)')
            _add_column_if_missing(conn, 'audit_log', cols, 'details', 'JSON')
            conn.execute(text("UPDATE audit_log SET timestamp = now() WHERE timestamp IS NULL"))
            conn.execute(text("UPDATE audit_log SET action = 'legacy' WHERE action IS NULL OR action = ''"))

        if 'app_settings' in tables:
            cols = _columns('app_settings')
            _add_column_if_missing(conn, 'app_settings', cols, 'value', "JSON DEFAULT '{}'::json")
            _add_column_if_missing(conn, 'app_settings', cols, 'updated_at', 'TIMESTAMP WITH TIME ZONE DEFAULT now()')
            conn.execute(text("UPDATE app_settings SET value = '{}'::json WHERE value IS NULL"))
            conn.execute(text("UPDATE app_settings SET updated_at = now() WHERE updated_at IS NULL"))


def bootstrap_database() -> None:
    migrate_existing_schema()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        normalize_existing_users(db)


def _has_password(user: User | None) -> bool:
    return bool(user and user.password_hash and user.password_hash.strip())


def normalize_existing_users(db: Session) -> None:
    """Clean up legacy duplicate users without provisioning default accounts.

    New installations intentionally start with no users. The unauthenticated
    /api/install/admin endpoint remains available until an active admin with a
    stored password hash exists. Existing installations keep their configured
    users, while older duplicate rows are made inactive for deterministic login.
    """
    admin_users = db.query(User).filter(User.role == UserRole.admin).order_by(User.id).all()
    viewer_users = db.query(User).filter(User.role == UserRole.viewer).order_by(User.id).all()

    admin = next((candidate for candidate in admin_users if candidate.is_active and _has_password(candidate)), None)
    if admin is None:
        admin = next((candidate for candidate in admin_users if _has_password(candidate)), None)

    viewer = next((candidate for candidate in viewer_users if candidate.is_active and _has_password(candidate)), None)
    if viewer is None:
        viewer = next((candidate for candidate in viewer_users if _has_password(candidate)), None)

    for duplicate in admin_users:
        if admin is not None and duplicate.id != admin.id:
            duplicate.is_active = False
            duplicate.totp_enabled = False
            duplicate.totp_secret = None
            delete_recovery_codes(db, duplicate)
            db.add(duplicate)

    for duplicate in viewer_users:
        if viewer is not None and duplicate.id != viewer.id:
            duplicate.is_active = False
            duplicate.totp_enabled = False
            duplicate.totp_secret = None
            delete_recovery_codes(db, duplicate)
            db.add(duplicate)

    if admin is not None:
        admin.is_active = True
        db.add(admin)

    # Viewer must never have Setup/2FA rights, even when migrating an old test database.
    if viewer is not None:
        viewer.is_active = True
        viewer.totp_enabled = False
        viewer.totp_secret = None
        delete_recovery_codes(db, viewer)
        db.add(viewer)

    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_database()
    poller.start()
    kindle_display_service.start()
    yield
    await kindle_display_service.stop()
    await poller.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, version='0.7.2', lifespan=lifespan)

configured_origins = [origin.strip() for origin in settings.frontend_origin.split(',') if origin.strip()]
loopback_hosts = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}
only_loopback_origins = bool(configured_origins) and all(
    urlparse(origin).hostname in loopback_hosts for origin in configured_origins if origin != '*'
)
allow_all_origins = not configured_origins or '*' in configured_origins or only_loopback_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'] if allow_all_origins else configured_origins,
    # BPSTracker uses Bearer tokens, not browser cookies. With allow_credentials=False we can safely
    # support LAN deployments where the frontend may be opened via hostname or IP address. Old .env
    # files with FRONTEND_ORIGIN=http://localhost:5173 are treated as local/LAN mode as well.
    allow_credentials=False if allow_all_origins else True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(install.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(measurements.router)
app.include_router(settings_router.router)
app.include_router(kindle.router)
app.include_router(maintenance.router)
app.include_router(backups.router)
app.include_router(current_values.router)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}
