from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_SECRET_MARKERS = ("token", "secret", "password", "passwd", "api_key", "credential")


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    INTEGRATION_UNAVAILABLE = "integration-unavailable"
    TOOL_EXECUTION = "tool-execution"
    TOOL_TIMEOUT = "tool-timeout"
    TOOL_OUTPUT = "tool-output"
    UPSTREAM = "upstream"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


def redact(value: Any, key: str = "") -> Any:
    if any(marker in key.lower() for marker in _SECRET_MARKERS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            item_key: redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class StructuredError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ErrorCategory
    code: str
    safe_message: str
    retryable: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=0)
    integration_id: str | None = None
    integration_details: dict[str, Any] = Field(default_factory=dict)

    def safe_dump(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["integration_details"] = redact(data["integration_details"])
        return data
