from enum import StrEnum

from pydantic import Field

from .common import ContractModel


class DependencyRelationshipType(StrEnum):
    DEPENDS_ON = "depends-on"
    DEV_DEPENDS_ON = "dev-depends-on"
    OPTIONAL_DEPENDS_ON = "optional-depends-on"
    CONTAINS = "contains"


class DependencyRelationship(ContractModel):
    target_component_id: str
    relationship: DependencyRelationshipType


class SourceReference(ContractModel):
    repository: str | None = None
    path: str | None = None
    commit: str | None = None


class Component(ContractModel):
    id: str
    name: str
    version: str | None = None
    purl: str | None = None
    ecosystem: str | None = None
    supplier: str | None = None
    licenses: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)
    dependency_relationships: list[DependencyRelationship] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)
