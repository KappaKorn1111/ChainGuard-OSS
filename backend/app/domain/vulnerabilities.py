from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import ContractModel, ToolProvenance


class CVSS(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    vector: str | None = None
    score: float = Field(ge=0, le=10)


class Vulnerability(ContractModel):
    id: str
    aliases: list[str] = Field(default_factory=list)
    source_database: str
    severity: str | None = None
    cvss: list[CVSS] = Field(default_factory=list)
    affected_package: str
    affected_range: str | None = None
    fixed_version: str | None = None
    advisory_references: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    modified_at: datetime | None = None
    provenance: ToolProvenance
