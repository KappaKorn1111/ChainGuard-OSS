from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select

from ..audit import write_audit_log
from ..config import get_settings
from ..dependencies import CurrentPrincipal, DbSession
from ..errors import APIError, request_id
from ..models import (
    MembershipRole,
    Organization,
    OrganizationMembership,
    User,
)
from ..rate_limit import rate_limit
from ..schemas import (
    BootstrapRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from ..security import (
    hash_password,
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
    validate_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
AuthRateLimit = Annotated[None, Depends(rate_limit(auth=True))]
_DUMMY_PASSWORD_HASH = hash_password("NotARealCredential123456789")


@router.post("/bootstrap", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    db: DbSession,
    _: AuthRateLimit,
) -> TokenResponse:
    settings = get_settings()
    validate_password(payload.password, settings)
    db.execute(select(func.pg_advisory_xact_lock(0x434841494E475541)))
    if db.scalar(select(func.count()).select_from(User)):
        raise APIError(409, "bootstrap_complete", "initial administrator already exists")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        is_superuser=True,
    )
    organization = Organization(name=payload.organization_name, slug=payload.organization_slug)
    db.add_all([user, organization])
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.owner,
        )
    )
    pair, _ = issue_token_pair(db, user, organization.id, settings)
    write_audit_log(
        db,
        action="auth.bootstrap",
        target_type="user",
        target_id=str(user.id),
        actor_user_id=user.id,
        organization_id=organization.id,
        correlation_id=request_id(request),
    )
    db.commit()
    return TokenResponse.model_validate(pair.model_dump())


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
    _: AuthRateLimit,
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    valid = verify_password(
        payload.password,
        user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
    )
    if user is None or not valid or not user.is_active:
        write_audit_log(
            db,
            action="auth.login_failed",
            target_type="user",
            target_id=str(user.id) if user else None,
            actor_user_id=user.id if user else None,
            correlation_id=request_id(request),
        )
        db.commit()
        raise APIError(401, "invalid_credentials", "email or password is incorrect")
    memberships = list(
        db.execute(
            select(OrganizationMembership, Organization)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(OrganizationMembership.user_id == user.id)
            .order_by(OrganizationMembership.created_at)
        ).all()
    )
    selected = next(
        (
            (membership, organization)
            for membership, organization in memberships
            if payload.organization_slug is None or organization.slug == payload.organization_slug
        ),
        None,
    )
    if selected is None:
        write_audit_log(
            db,
            action="auth.login_failed",
            target_type="user",
            target_id=str(user.id),
            actor_user_id=user.id,
            correlation_id=request_id(request),
            details={"reason": "organization_unavailable"},
        )
        db.commit()
        raise APIError(401, "invalid_credentials", "email or password is incorrect")
    membership, organization = selected
    pair, _ = issue_token_pair(db, user, membership.organization_id, get_settings())
    write_audit_log(
        db,
        action="auth.login",
        target_type="user",
        target_id=str(user.id),
        actor_user_id=user.id,
        organization_id=organization.id,
        correlation_id=request_id(request),
    )
    db.commit()
    return TokenResponse.model_validate(pair.model_dump())


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: DbSession,
    _: AuthRateLimit,
) -> TokenResponse:
    pair, replacement = rotate_refresh_token(
        db,
        payload.refresh_token,
        get_settings(),
        correlation_id=request_id(request),
    )
    write_audit_log(
        db,
        action="auth.refresh",
        target_type="refresh_token",
        target_id=str(replacement.id),
        actor_user_id=replacement.user_id,
        organization_id=replacement.organization_id,
        correlation_id=request_id(request),
    )
    db.commit()
    return TokenResponse.model_validate(pair.model_dump())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: RefreshRequest,
    request: Request,
    db: DbSession,
    _: AuthRateLimit,
) -> None:
    revoke_refresh_token(db, payload.refresh_token, get_settings())
    write_audit_log(
        db,
        action="auth.logout",
        target_type="refresh_token",
        correlation_id=request_id(request),
    )
    db.commit()


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentPrincipal, db: DbSession) -> MeResponse:
    organization = db.get(Organization, principal.organization_id)
    if organization is None:
        raise APIError(404, "organization_not_found", "organization not found")
    return MeResponse(
        user=principal.user,
        organization=organization,
        role=principal.role,
    )
