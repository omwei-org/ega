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
    ao_ref: str | None = None
    aee_ref: str | None = None
    ect_ref: str | None = None


@dataclass(frozen=True)
class ExecutionAttestation:
    """Evidence record binding an execution decision to its authority and context."""
    execution_id: str
    authority_id: str
    authority_digest: str
    prepared_context_epoch: int
    current_context_epoch: int
    decision: str
    reason: str
    commit: str
    effect: str
