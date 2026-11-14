from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select

from ..audit import write_audit_log
from ..config import get_settings
from ..dependencies import CurrentPrincipal, DbSession, Principal, require_roles
from ..errors import APIError, request_id
from ..models import MembershipRole, OrganizationMembership, User
from ..schemas import Page, UserCreate, UserRead, UserUpdate
from ..security import hash_password, validate_password

router = APIRouter(prefix="/users", tags=["users"])
UserAdmin = Annotated[
    Principal, Depends(require_roles(MembershipRole.owner, MembershipRole.admin))
]


def tenant_user(db: DbSession, organization_id: UUID, user_id: UUID) -> User:
    user = db.scalar(
        select(User)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(
            User.id == user_id,
            OrganizationMembership.organization_id == organization_id,
        )
    )
    if user is None:
        raise APIError(404, "user_not_found", "user not found")
    return user


@router.get("", response_model=Page[UserRead])
def list_users(
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=200)] = None,
    active: bool | None = None,
) -> Page[UserRead]:
    query = (
        select(User)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(OrganizationMembership.organization_id == principal.organization_id)
    )
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(User.email.ilike(pattern), User.display_name.ilike(pattern)))
    if active is not None:
        query = query.where(User.is_active == active)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(db.scalars(query.order_by(User.email).offset(offset).limit(limit)))
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    principal: UserAdmin,
    db: DbSession,
) -> User:
    if payload.role == MembershipRole.owner and principal.role != MembershipRole.owner:
        raise APIError(403, "permission_denied", "only owners can create owners")
    validate_password(payload.password, get_settings())
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise APIError(409, "user_exists", "a user with this email already exists")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=principal.organization_id,
            user_id=user.id,
            role=payload.role,
        )
    )
    write_audit_log(
        db,
        action="user.create",
        target_type="user",
        target_id=str(user.id),
        actor_user_id=principal.user.id,
        organization_id=principal.organization_id,
        correlation_id=request_id(request),
        details={"role": payload.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, principal: CurrentPrincipal, db: DbSession) -> User:
    return tenant_user(db, principal.organization_id, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    principal: UserAdmin,
    db: DbSession,
) -> User:
    user = tenant_user(db, principal.organization_id, user_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    write_audit_log(
        db,
        action="user.update",
        target_type="user",
        target_id=str(user.id),
        actor_user_id=principal.user.id,
        organization_id=principal.organization_id,
        correlation_id=request_id(request),
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: UUID,
    request: Request,
    principal: UserAdmin,
    db: DbSession,
) -> None:
    user = tenant_user(db, principal.organization_id, user_id)
    if user.id == principal.user.id:
        raise APIError(409, "self_deactivation", "users cannot deactivate themselves")
    user.is_active = False
    write_audit_log(
        db,
        action="user.deactivate",
        target_type="user",
        target_id=str(user.id),
        actor_user_id=principal.user.id,
        organization_id=principal.organization_id,
        correlation_id=request_id(request),
    )
    db.commit()
