from datetime import datetime

from pydantic import Field

from .common import ContractModel
from .components import Component


class SBOMDocument(ContractModel):
    id: str
    format: str
    document_schema_version: str
    source_project: str
    source_repository: str | None = None
    commit: str | None = None
    artifact_checksum: str | None = None
    generated_at: datetime
    generator_identity: str
    generator_version: str | None = None
    original_artifact_location: str
    components: list[Component] = Field(default_factory=list)
