from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select

from ..audit import write_audit_log
from ..dependencies import CurrentPrincipal, DbSession, Principal, require_roles
from ..errors import APIError, request_id
from ..models import MembershipRole, Project
from ..schemas import Page, ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])
ProjectWriter = Annotated[
    Principal,
    Depends(
        require_roles(
            MembershipRole.owner,
            MembershipRole.admin,
            MembershipRole.member,
        )
    ),
]
ProjectAdmin = Annotated[
    Principal, Depends(require_roles(MembershipRole.owner, MembershipRole.admin))
]


def tenant_project(db: DbSession, organization_id: UUID, project_id: UUID) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
        )
    )
    if project is None:
        raise APIError(404, "project_not_found", "project not found")
    return project


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[ProjectRead]:
    query = select(Project).where(Project.organization_id == principal.organization_id)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Project.name.ilike(pattern), Project.slug.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(db.scalars(query.order_by(Project.name).offset(offset).limit(limit)))
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    principal: ProjectWriter,
    db: DbSession,
) -> Project:
    project = Project(
        organization_id=principal.organization_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
    )
    db.add(project)
    db.flush()
    write_audit_log(
        db,
        action="project.create",
        target_type="project",
        target_id=str(project.id),
        actor_user_id=principal.user.id,
        organization_id=principal.organization_id,
        correlation_id=request_id(request),
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, principal: CurrentPrincipal, db: DbSession) -> Project:
    return tenant_project(db, principal.organization_id, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    principal: ProjectWriter,
    db: DbSession,
) -> Project:
    project = tenant_project(db, principal.organization_id, project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    write_audit_log(
        db,
        action="project.update",
        target_type="project",
        target_id=str(project.id),
        actor_user_id=principal.user.id,
        organization_id=principal.organization_id,
        correlation_id=request_id(request),
    )
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    request: Request,
    principal: ProjectAdmin,
    db: DbSession,
) -> None:
    project = tenant_project(db, principal.organization_id, project_id)
    write_audit_log(
        db,
        action="project.delete",
        target_type="project",
        target_id=str(project.id),
        actor_user_id=principal.user.id,
        organization_id=principal.organization_id,
        correlation_id=request_id(request),
    )
    db.delete(project)
    db.commit()
