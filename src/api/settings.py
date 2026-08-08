"""Configuration for the incident API.

The project's first real settings module. Everything before this reached for
`os.getenv` at import time scattered across modules, which is why connection
strings ended up hardcoded to 127.0.0.1 in five places and a live SigNoz token
ended up as a literal default in `src/production/main.py`.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres. Host port 5433 — 5432 is left free for a developer's local
    # install, and SigNoz's own metastore Postgres is unpublished.
    database_url: str = "postgresql://incimin:incimin@127.0.0.1:5433/incimin"
    db_pool_min: int = 1
    db_pool_max: int = 10

    # API. 8088 is registered in docs/PORTS.md. 8080 is reserved-unbound
    # project-wide and must never be used.
    api_host: str = "127.0.0.1"
    api_port: int = 8088

    # Agent execution.
    webhook_max_steps: int = 10
    webhook_max_concurrency: int = 2
    webhook_target: str = "agent"

    log_level: str = "INFO"


settings = Settings()
