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
