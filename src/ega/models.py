from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class RuntimeIntent:
    principal: str
    action: str
    target: str
    parameters: dict[str, Any]
    environment: str
    decision_ref: str

@dataclass(frozen=True)
class ExecutionAuthority:
    authority_id: str
    principal: str
    action: str
    target: str
    parameters: dict[str, Any]
    environment: str
    source_decision: str
    status: str = "VALID"
