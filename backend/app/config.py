from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://chainguard:chainguard@postgres:5432/chainguard"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    upload_dir: Path = Path("/data/uploads")
    max_upload_bytes: int = 536_870_912
    scan_timeout_seconds: int = 900
    scanner_memory_limit_mb: int = 2048
    dependency_track_url: str | None = None
    dependency_track_api_key: str | None = None
    dependency_track_project_name: str = "ChainGuard OSS"
    dependency_track_project_version: str = "continuous"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("max_upload_bytes", "scan_timeout_seconds", "scanner_memory_limit_mb")
    @classmethod
    def positive_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("resource limits must be positive")
        return value

    @property
    def dependency_track_enabled(self) -> bool:
        return bool(self.dependency_track_url and self.dependency_track_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
