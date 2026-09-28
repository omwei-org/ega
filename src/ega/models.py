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
class EvidenceItem:
    """EGA-side reference to an upstream evidence item.

    The item records provenance and decision-use classification; it does not
    assert the truth of the upstream evidence or its source-reported confidence.
    """
    evidence_ref: str
    digest: str
    observed_at: str
    evaluation_status: str
    role: str | None = None
    source_confidence: float | None = None

@dataclass(frozen=True)
class DecisionRecord:
    """EGA-side record explaining why execution authority was issued.

    This is not an EABC primitive. It preserves the full RAIG evidence
    population considered by EGA, including evidence that was evaluated but
    excluded from the authority decision.
    """
    decision_id: str
    decision_time: str
    intent_ref: str
    authorization_scope_ref: str
    evidence_items: tuple[EvidenceItem, ...] = field(default_factory=tuple)

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
    ao_ref: str | None = None
    aee_ref: str | None = None
    ect_ref: str | None = None
    decision_record_ref: str | None = None
    decision_record_digest: str | None = None
    selected_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
