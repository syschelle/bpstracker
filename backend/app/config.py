from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = 'BPSTracker'
    database_url: str = 'postgresql+psycopg://bpstracker:bpstracker_dev_password@postgres:5432/bpstracker'
    secret_key: str = 'change-me'
    access_token_expire_minutes: int = 720
    # Comma-separated list of allowed browser origins. Use '*' for local/LAN deployments.
    frontend_origin: str = '*'
    polling_loop_seconds: int = 5
    shelly_timeout_seconds: float = 5.0
    shelly_max_concurrency: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
