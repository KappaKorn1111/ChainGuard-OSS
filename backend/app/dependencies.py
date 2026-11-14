from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .errors import APIError
from .models import MembershipRole, OrganizationMembership, User
from .security import decode_token

DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class Principal:
    user: User
    organization_id: uuid.UUID
    role: MembershipRole


def current_principal(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise APIError(401, "authentication_required", "authentication is required")
    claims = decode_token(authorization.removeprefix("Bearer ").strip(), get_settings(), "access")
    try:
        user_id = uuid.UUID(claims["sub"])
        organization_id = uuid.UUID(claims["org"])
    except (KeyError, ValueError) as exc:
        raise APIError(401, "invalid_token", "authentication credentials are invalid") from exc
    user = db.get(User, user_id)
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
        )
    )
    if user is None or not user.is_active or membership is None:
        raise APIError(401, "invalid_token", "authentication credentials are invalid")
    return Principal(user=user, organization_id=organization_id, role=membership.role)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: MembershipRole):
    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.user.is_superuser or principal.role in roles:
            return principal
        raise APIError(403, "permission_denied", "insufficient permissions")

    return dependency
