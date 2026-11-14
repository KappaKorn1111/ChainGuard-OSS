from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from .common import ContractModel


class ScanStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed-out"
    PARTIALLY_COMPLETED = "partially-completed"


class FailureInfo(ContractModel):
    category: str
    safe_message: str
    retryable: bool = False
    integration_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ResourceUsage(ContractModel):
    cpu_seconds: float | None = Field(default=None, ge=0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)
    stdout_bytes: int = Field(default=0, ge=0)
    stderr_bytes: int = Field(default=0, ge=0)


class ScanExecution(ContractModel):
    scan_id: str
    project_id: str
    integration_id: str
    status: ScanStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tool_version: str | None = None
    source_revision: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    resource_usage: ResourceUsage | None = None
    failure: FailureInfo | None = None
    correlation_id: str
    idempotency_key: str

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "ScanExecution":
        terminal = {
            ScanStatus.COMPLETED,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
            ScanStatus.TIMED_OUT,
            ScanStatus.PARTIALLY_COMPLETED,
        }
        if self.status in terminal and self.completed_at is None:
            raise ValueError("terminal scan states require completed_at")
        if self.status in {ScanStatus.FAILED, ScanStatus.TIMED_OUT} and self.failure is None:
            raise ValueError("failed and timed-out scans require failure information")
        return self


VALID_SCAN_TRANSITIONS: dict[ScanStatus, frozenset[ScanStatus]] = {
    ScanStatus.PENDING: frozenset({ScanStatus.QUEUED, ScanStatus.CANCELLED}),
    ScanStatus.QUEUED: frozenset({ScanStatus.RUNNING, ScanStatus.CANCELLED}),
    ScanStatus.RUNNING: frozenset(
        {
            ScanStatus.COMPLETED,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
            ScanStatus.TIMED_OUT,
            ScanStatus.PARTIALLY_COMPLETED,
        }
    ),
    ScanStatus.COMPLETED: frozenset(),
    ScanStatus.FAILED: frozenset({ScanStatus.QUEUED}),
    ScanStatus.CANCELLED: frozenset(),
    ScanStatus.TIMED_OUT: frozenset({ScanStatus.QUEUED}),
    ScanStatus.PARTIALLY_COMPLETED: frozenset({ScanStatus.QUEUED}),
}


def validate_scan_transition(current: ScanStatus, target: ScanStatus) -> None:
    if target not in VALID_SCAN_TRANSITIONS[current]:
        raise ValueError(f"invalid scan transition: {current.value} -> {target.value}")
