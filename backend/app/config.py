from functools import lru_cache
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
