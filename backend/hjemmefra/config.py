from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HJEMMEFRA_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./hjemmefra.db"
    admin_api_key: str = ""  # must be set via environment in production
    seed_demo: bool = False
    demo_api_key: str = "demo-key"  # only used when seed_demo is true
    log_level: str = "INFO"
    optimizer_default_time_limit: float = 10.0
    # external sources (all optional; adapters report 'missing token' instead of failing hard)
    salling_api_token: str = ""
    tjek_api_key: str = ""
    source_postal_code: str = ""  # area to ingest offers for
    source_radius_m: int = 10000


settings = Settings()
