import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_configuration_loads_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example,https://admin.example")
    settings = Settings(_env_file=None)
    assert settings.environment == "production"
    assert settings.cors_origins == ["https://app.example", "https://admin.example"]


def test_configuration_rejects_unbounded_scans() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, scan_timeout_seconds=0)


def test_production_requires_strong_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError, match="32"):
        Settings(_env_file=None, environment="production", jwt_secret="too-short")


def test_configuration_rejects_sqlite_and_unsafe_cors() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(_env_file=None, database_url="sqlite:///test.db")
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(
            _env_file=None,
            cors_origins=["*"],
            cors_allow_credentials=True,
        )
