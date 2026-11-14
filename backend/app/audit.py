from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def write_audit_log(
    db: Session,
    *,
    action: str,
    target_type: str,
    correlation_id: str,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id,
            details=details or {},
        )
    )
