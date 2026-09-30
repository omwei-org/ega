from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from .evidence import canonical_json


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Minimal Observer → governance evidence interoperability contract.

    This contract carries evidence only. It contains no authorization,
    materiality, policy, commit-condition, or enforcement semantics.
    """

    schema_version: str
    evidence_id: str
    subject: str
    state: str
    observed_at: str
    freshness: str
    temporal_basis: str
    provenance: str
    value: Any = None
    uncertainty: float | None = None
    source_confidence: float | None = None
    integrity_ref: str = ""


def _integrity_payload(envelope: EvidenceEnvelope) -> dict[str, Any]:
    return {
        "schema_version": envelope.schema_version,
        "evidence_id": envelope.evidence_id,
        "subject": envelope.subject,
        "state": envelope.state,
        "observed_at": envelope.observed_at,
        "freshness": envelope.freshness,
        "temporal_basis": envelope.temporal_basis,
        "provenance": envelope.provenance,
        "value": envelope.value,
        "uncertainty": envelope.uncertainty,
        "source_confidence": envelope.source_confidence,
    }


def evidence_envelope_integrity_ref(envelope: EvidenceEnvelope) -> str:
    """Return SHA-256 over the canonical evidence payload."""
    return sha256(canonical_json(_integrity_payload(envelope))).hexdigest()


def validate_evidence_envelope(envelope: EvidenceEnvelope) -> None:
    if not envelope.schema_version:
        raise ValueError("schema_version is required")
    if not envelope.evidence_id:
        raise ValueError("evidence_id is required")
    if not envelope.subject:
        raise ValueError("subject is required")
    if not envelope.state:
        raise ValueError("state is required")
    if not envelope.observed_at:
        raise ValueError("observed_at is required")
    if not envelope.temporal_basis:
        raise ValueError("temporal_basis is required")
    if not envelope.provenance:
        raise ValueError("provenance is required")
    try:
        parsed = datetime.fromisoformat(envelope.observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    if not 0.0 <= (envelope.uncertainty if envelope.uncertainty is not None else 0.0) <= 1.0:
        raise ValueError("uncertainty must be between 0 and 1")
    if envelope.source_confidence is not None and not 0.0 <= envelope.source_confidence <= 1.0:
        raise ValueError("source_confidence must be between 0 and 1")
    if not envelope.integrity_ref:
        raise ValueError("integrity_ref is required")
    expected = evidence_envelope_integrity_ref(envelope)
    if envelope.integrity_ref != expected:
        raise ValueError("evidence envelope integrity_ref does not match canonical payload")


def evidence_envelope_to_evidence(
    envelope: EvidenceEnvelope,
    *,
    evaluation_status: str,
    role: str | None = None,
):
    """Normalize the generic evidence contract into EGA's internal evidence model.

    The adapter preserves evidence and assigns no materiality or authority.
    The caller supplies the EGA-side evaluation classification explicitly.
    """
    from .models import EvidenceItem

    validate_evidence_envelope(envelope)
    return EvidenceItem(
        evidence_ref=envelope.evidence_id,
        digest=envelope.integrity_ref,
        observed_at=envelope.observed_at,
        evaluation_status=evaluation_status,
        role=role,
        target=envelope.subject,
        state=envelope.state,
        value=envelope.value,
        freshness=envelope.freshness,
        uncertainty=envelope.uncertainty,
        source_confidence=envelope.source_confidence,
        provenance=envelope.provenance,
    )
