"""EGA reference implementation."""

from .models import (
    AuthorizationScope,
    DecisionRecord,
    EvidenceItem,
    ExecutionAuthority,
    ExecutionAttestation,
    ObserverObservation,
    RuntimeIntent,
)
from .interop import EvidenceEnvelope, evidence_envelope_integrity_ref
from .observer import evidence_envelope_to_ega, observation_to_evidence
from .authority import AuthorizationError, issue_authority
from .boundary import (
    PreparedAuthority,
    commit,
    execution_attestation,
    final_authority_check,
    prepare,
)

__all__ = [
    "AuthorizationError",
    "AuthorizationScope",
    "DecisionRecord",
    "EvidenceEnvelope",
    "EvidenceItem",
    "ExecutionAuthority",
    "ExecutionAttestation",
    "ObserverObservation",
    "PreparedAuthority",
    "RuntimeIntent",
    "commit",
    "evidence_envelope_integrity_ref",
    "evidence_envelope_to_ega",
    "execution_attestation",
    "final_authority_check",
    "issue_authority",
    "observation_to_evidence",
    "prepare",
]
