from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = 'BPSTracker'
    database_url: str = 'postgresql+psycopg://bpstracker:change-me-database-password@postgres:5432/bpstracker'
    secret_key: str = 'change-me'
    access_token_expire_minutes: int = 720
    # Browser auth is stored in an HttpOnly cookie. Keep secure=False for plain HTTP/LAN installs;
    # set AUTH_COOKIE_SECURE=true when BPSTracker is served only via HTTPS.
    auth_cookie_name: str = 'bpstracker_access_token'
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = 'lax'
    # Comma-separated list of allowed browser origins. Use explicit origins for cross-origin dev setups.
    frontend_origin: str = '*'
    polling_loop_seconds: int = 5
    shelly_timeout_seconds: float = 5.0
    shelly_max_concurrency: int = 4
    # Optional low-resource profile for Raspberry Pi Zero 2 W deployments.
    # When enabled, only the latest 24h of raw/live data are retained and served by default,
    # while permanent daily aggregates keep total balances available.
    pi_zero_2w_mode: bool = False
    live_data_max_hours: int = 0
    raw_retention_hours: int = 0
    default_language: str = Field(default='de', validation_alias='BPSTRACKER_DEFAULT_LANGUAGE')


@lru_cache
def get_settings() -> Settings:
    return Settings()
