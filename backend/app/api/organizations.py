from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select

from ..audit import write_audit_log
from ..dependencies import CurrentPrincipal, DbSession, Principal, require_roles
from ..errors import APIError, request_id
from ..models import MembershipRole, Organization, OrganizationMembership, User
from ..schemas import (
    MembershipCreate,
    MembershipRead,
    MembershipUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    Page,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])
OrgAdmin = Annotated[
    Principal, Depends(require_roles(MembershipRole.owner, MembershipRole.admin))
]
OrgOwner = Annotated[Principal, Depends(require_roles(MembershipRole.owner))]


def require_current_org(organization_id: UUID, principal: Principal) -> None:
    if not principal.user.is_superuser and organization_id != principal.organization_id:
        raise APIError(404, "organization_not_found", "organization not found")


@router.get("", response_model=Page[OrganizationRead])
def list_organizations(
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[OrganizationRead]:
    query = (
        select(Organization)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(OrganizationMembership.user_id == principal.user.id)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(db.scalars(query.order_by(Organization.name).offset(offset).limit(limit)))
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> Organization:
    organization = Organization(name=payload.name, slug=payload.slug)
    db.add(organization)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=principal.user.id,
            role=MembershipRole.owner,
        )
    )
    write_audit_log(
        db,
        action="organization.create",
        target_type="organization",
        target_id=str(organization.id),
        actor_user_id=principal.user.id,
        organization_id=organization.id,
        correlation_id=request_id(request),
    )
    db.commit()
    db.refresh(organization)
    return organization


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: UUID,
    principal: CurrentPrincipal,
    db: DbSession,
) -> Organization:
    require_current_org(organization_id, principal)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise APIError(404, "organization_not_found", "organization not found")
    return organization


@router.patch("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    request: Request,
    principal: OrgAdmin,
    db: DbSession,
) -> Organization:
    require_current_org(organization_id, principal)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise APIError(404, "organization_not_found", "organization not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, key, value)
    write_audit_log(
        db,
        action="organization.update",
        target_type="organization",
        target_id=str(organization.id),
        actor_user_id=principal.user.id,
        organization_id=organization.id,
        correlation_id=request_id(request),
    )
    db.commit()
    db.refresh(organization)
    return organization


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: UUID,
    request: Request,
    principal: OrgOwner,
    db: DbSession,
) -> None:
    require_current_org(organization_id, principal)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise APIError(404, "organization_not_found", "organization not found")
    write_audit_log(
        db,
        action="organization.delete",
        target_type="organization",
        target_id=str(organization.id),
        actor_user_id=principal.user.id,
        organization_id=None,
        correlation_id=request_id(request),
    )
    db.delete(organization)
    db.commit()


@router.get("/{organization_id}/memberships", response_model=Page[MembershipRead])
def list_memberships(
    organization_id: UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MembershipRead]:
    require_current_org(organization_id, principal)
    query = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(query.order_by(OrganizationMembership.created_at).offset(offset).limit(limit))
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{organization_id}/memberships",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_membership(
    organization_id: UUID,
    payload: MembershipCreate,
    request: Request,
    principal: OrgAdmin,
    db: DbSession,
) -> OrganizationMembership:
    require_current_org(organization_id, principal)
    if payload.role == MembershipRole.owner and principal.role != MembershipRole.owner:
        raise APIError(403, "permission_denied", "only owners can add owners")
    if db.get(User, payload.user_id) is None:
        raise APIError(404, "user_not_found", "user not found")
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    db.add(membership)
    db.flush()
    write_audit_log(
        db,
        action="membership.create",
        target_type="membership",
        target_id=str(membership.id),
        actor_user_id=principal.user.id,
        organization_id=organization_id,
        correlation_id=request_id(request),
        details={"user_id": str(payload.user_id), "role": payload.role.value},
    )
    db.commit()
    db.refresh(membership)
    return membership


@router.patch("/{organization_id}/memberships/{membership_id}", response_model=MembershipRead)
def update_membership(
    organization_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
    request: Request,
    principal: OrgAdmin,
    db: DbSession,
) -> OrganizationMembership:
    require_current_org(organization_id, principal)
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise APIError(404, "membership_not_found", "membership not found")
    if (
        membership.role == MembershipRole.owner or payload.role == MembershipRole.owner
    ) and principal.role != MembershipRole.owner:
        raise APIError(403, "permission_denied", "only owners can change owner roles")
    membership.role = payload.role
    write_audit_log(
        db,
        action="membership.update",
        target_type="membership",
        target_id=str(membership.id),
        actor_user_id=principal.user.id,
        organization_id=organization_id,
        correlation_id=request_id(request),
        details={"role": payload.role.value},
    )
    db.commit()
    db.refresh(membership)
    return membership


@router.delete(
    "/{organization_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_membership(
    organization_id: UUID,
    membership_id: UUID,
    request: Request,
    principal: OrgAdmin,
    db: DbSession,
) -> None:
    require_current_org(organization_id, principal)
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise APIError(404, "membership_not_found", "membership not found")
    if membership.role == MembershipRole.owner:
        owners = db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == MembershipRole.owner,
            )
        )
        if owners == 1:
            raise APIError(409, "last_owner", "the last organization owner cannot be removed")
        if principal.role != MembershipRole.owner:
            raise APIError(403, "permission_denied", "only owners can remove owners")
    write_audit_log(
        db,
        action="membership.delete",
        target_type="membership",
        target_id=str(membership.id),
        actor_user_id=principal.user.id,
        organization_id=organization_id,
        correlation_id=request_id(request),
    )
    db.delete(membership)
    db.commit()
