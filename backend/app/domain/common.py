from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ContractVersion = Literal["1.0"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: ContractVersion = "1.0"
    tenant_id: str = Field(min_length=1)


class TransformationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transformer: str
    transformer_version: str | None = None
    timestamp: datetime
    operation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolProvenance(ContractModel):
    tool_identity: str
    tool_version: str | None = None
    original_data_source: str
    original_record_id: str
    artifact_checksum: str | None = None
    collection_timestamp: datetime
    transformation_history: list[TransformationStep] = Field(default_factory=list)
    test_only: bool = False

    @field_validator("artifact_checksum")
    @classmethod
    def validate_checksum(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("sha256:", "sha512:")):
            raise ValueError("artifact checksum must include a supported algorithm prefix")
        return value
