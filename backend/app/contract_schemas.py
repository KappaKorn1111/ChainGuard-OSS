from pydantic import BaseModel

from .domain import (
    Component,
    SBOMDocument,
    ScanExecution,
    SecurityFinding,
    ToolProvenance,
    Vulnerability,
)

CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "component-v1": Component,
    "sbom-document-v1": SBOMDocument,
    "scan-execution-v1": ScanExecution,
    "security-finding-v1": SecurityFinding,
    "tool-provenance-v1": ToolProvenance,
    "vulnerability-v1": Vulnerability,
}
