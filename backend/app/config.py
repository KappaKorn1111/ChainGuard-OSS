import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    database_url: str = "postgresql+psycopg://postgres:5432/chainguard"
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
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "chainguard-oss"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    password_min_length: int = 12
    cors_allow_credentials: bool = False
    auth_rate_limit: int = 10
    api_rate_limit: int = 120
    rate_limit_window_seconds: int = 60
    migration_head: str = "0002"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "max_upload_bytes",
        "scan_timeout_seconds",
        "scanner_memory_limit_mb",
        "access_token_minutes",
        "refresh_token_days",
        "password_min_length",
        "auth_rate_limit",
        "api_rate_limit",
        "rate_limit_window_seconds",
    )
    @classmethod
    def positive_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("resource limits must be positive")
        return value

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        return value

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError("wildcard CORS origins cannot be used with credentials")
        if self.jwt_secret is None:
            if self.environment != "development":
                raise ValueError("JWT_SECRET is required outside development")
            self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
        elif len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        if self.password_min_length < 12:
            raise ValueError("PASSWORD_MIN_LENGTH must be at least 12")
        return self

    @property
    def dependency_track_enabled(self) -> bool:
        return bool(self.dependency_track_url and self.dependency_track_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
