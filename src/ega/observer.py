from __future__ import annotations

from .models import EvidenceItem, ObserverObservation


def observation_to_evidence(
    observation: ObserverObservation,
    *,
    evaluation_status: str,
    role: str | None = None,
) -> EvidenceItem:
    """Normalize one read-only Observer observation into EGA evidence.

    The Observer supplies the observation and its provenance/quality metadata.
    EGA supplies only the decision-use classification (status and role).
    """
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
