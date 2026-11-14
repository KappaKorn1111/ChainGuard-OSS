from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Set
from typing import Any

from pydantic import BaseModel

from .models import (
    Capability,
    ExecutionRequirements,
    IntegrationHealth,
    IntegrationIdentity,
    IntegrationResult,
    VersionInfo,
)


class Integration[InputT: BaseModel](ABC):
    """Base contract implemented by every external integration adapter."""

    test_only: bool = False

    @property
    @abstractmethod
    def identity(self) -> IntegrationIdentity: ...

    @property
    @abstractmethod
    def version(self) -> VersionInfo: ...

    @property
    @abstractmethod
    def capabilities(self) -> Set[Capability]: ...

    @property
    @abstractmethod
    def execution_requirements(self) -> ExecutionRequirements: ...

    @property
    @abstractmethod
    def input_formats(self) -> Set[str]: ...

    @property
    @abstractmethod
    def output_formats(self) -> Set[str]: ...

    @abstractmethod
    def validate_config(self, config: Mapping[str, Any]) -> tuple[str, ...]:
        """Return safe validation errors; an empty tuple means valid."""

    @abstractmethod
    async def health_check(self) -> IntegrationHealth: ...

    @abstractmethod
    async def execute(self, request: InputT) -> IntegrationResult:
        """Raise IntegrationError for expected adapter failures."""


class SBOMGenerator[InputT: BaseModel](Integration[InputT], ABC): ...


class SBOMNormalizer[InputT: BaseModel](Integration[InputT], ABC): ...


class VulnerabilityScanner[InputT: BaseModel](Integration[InputT], ABC): ...


class VulnerabilityIntelligenceProvider[InputT: BaseModel](Integration[InputT], ABC): ...


class ComponentAnalysisProvider[InputT: BaseModel](Integration[InputT], ABC): ...


class RepositoryRiskProvider[InputT: BaseModel](Integration[InputT], ABC): ...


class SupplyChainGraphProvider[InputT: BaseModel](Integration[InputT], ABC): ...


class ProvenanceVerifier[InputT: BaseModel](Integration[InputT], ABC): ...


class ArtifactSignatureVerifier[InputT: BaseModel](Integration[InputT], ABC): ...


class ContainerScanner[InputT: BaseModel](Integration[InputT], ABC): ...


class SourceCodeScanner[InputT: BaseModel](Integration[InputT], ABC): ...


class InfrastructureScanner[InputT: BaseModel](Integration[InputT], ABC): ...


class SecurityFindingsProvider[InputT: BaseModel](Integration[InputT], ABC): ...
