from __future__ import annotations

from .interop import EvidenceEnvelope, evidence_envelope_to_evidence
from .models import EvidenceItem, ObserverObservation


def observation_to_evidence(
    observation: ObserverObservation,
    *,
    evaluation_status: str,
    role: str | None = None,
) -> EvidenceItem:
    """Backward-compatible adapter for the original EGA-local observation model."""
    if not observation.observation_ref:
        raise ValueError("observation_ref is required")
    if not observation.target:
        raise ValueError("observation target is required")
    if not observation.observed_at:
        raise ValueError("observed_at is required")
    if not observation.digest:
        raise ValueError("observer observation digest is required")
    if not 0.0 <= (observation.uncertainty if observation.uncertainty is not None else 0.0) <= 1.0:
        raise ValueError("uncertainty must be between 0 and 1")

    return EvidenceItem(
        evidence_ref=observation.observation_ref,
        digest=observation.digest,
        observed_at=observation.observed_at,
        evaluation_status=evaluation_status,
        role=role,
        target=observation.target,
        state=observation.state,
        value=observation.value,
        freshness=observation.freshness,
        uncertainty=observation.uncertainty,
        provenance=observation.provenance,
    )


def evidence_envelope_to_ega(
    envelope: EvidenceEnvelope,
    *,
    evaluation_status: str,
    role: str | None = None,
) -> EvidenceItem:
    """Adapter from the interoperable evidence envelope into EGA evidence."""
    return evidence_envelope_to_evidence(
        envelope,
        evaluation_status=evaluation_status,
        role=role,
    )
