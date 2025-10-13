"""Application configuration via Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    bot_token: str = Field(..., env="BOT_TOKEN")
    database_url: str = Field(..., env="DATABASE_URL")
    redis_url: str = Field(..., env="REDIS_URL")
    owner_telegram_id: int = Field(..., env="OWNER_TELEGRAM_ID")
    timezone: str = Field("Europe/Sofia", env="TZ")
    phone_salt: str = Field(..., env="PHONE_SALT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    scheduler_timezone: str = Field("UTC", env="SCHEDULER_TZ")
    allowed_languages: List[str] = Field(default_factory=lambda: ["ru", "en"])

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("database_url")
    def _ensure_asyncpg(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("sqlite://") and "+aiosqlite" not in value:
            return value.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings(_env_file=Path(__file__).resolve().parent.parent / ".env")


settings = get_settings()
