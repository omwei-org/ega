from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class RuntimeIntent:
    principal: str
    action: str
    target: str
    parameters: dict[str, Any]
    environment: str
    decision_ref: str
    governance_context: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class AuthorizationScope:
    """Provisioning-time scope supplied to EGA; EGA never creates or modifies it."""
    principal: str
    action: str
    target: str
    environment: str
    parameter_constraints: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ExecutionAuthority:
    authority_id: str
    principal: str
    action: str
    target: str
    parameters: dict[str, Any]
    environment: str
    source_decision: str
    governance_context: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "VALID"
