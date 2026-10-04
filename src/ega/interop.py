from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
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


def _compute_freshness_from_observed_at(observed_at: str, max_age_seconds: int) -> str:
    """Compute FRESH/STALE from observed_at and EGA's freshness threshold.

    Observer EvidenceEnvelope v1 does not include freshness (INV-03).
    EGA evaluates freshness at evaluation time using the observation timestamp.
    """
    obs_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    age_seconds = (datetime.now(timezone.utc) - obs_time).total_seconds()
    return "FRESH" if age_seconds <= max_age_seconds else "STALE"


def _canonicalize_nextone_v1(payload: Any) -> bytes:
    """Canonicalize using nextone-canonical-json-v1 algorithm.

    Algorithm:
    1. JSON with deterministic key ordering (sorted by Unicode code point)
    2. Compact separators ("," and ":")
    3. UTF-8 encoding (ensure_ascii=False)
    """
    text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return text.encode("utf-8")


def _compute_observer_v1_integrity_digest(envelope_dict: dict[str, Any]) -> str:
    """Compute SHA-256 integrity digest using nextone-canonical-json-v1.

    The integrity payload is the complete envelope excluding the 'integrity' object.
    Returns digest with "sha256:" prefix.
    """
    covered = {k: v for k, v in envelope_dict.items() if k != "integrity"}
    digest = sha256(_canonicalize_nextone_v1(covered)).hexdigest()
    return f"sha256:{digest}"


def _verify_observer_v1_integrity(envelope_dict: dict[str, Any]) -> bool:
    """Verify that the envelope's integrity digest matches its canonical payload."""
    expected = _compute_observer_v1_integrity_digest(envelope_dict)
    actual = envelope_dict.get("integrity", {}).get("digest", "")
    return expected == actual


def _derive_observer_v1_evidence_id(
    subject: dict[str, Any],
    target: dict[str, Any],
    observed_state: str,
    observed_value: Any,
    observed_at: str,
    provenance: dict[str, Any],
) -> str:
    """Derive Observer v1 evidence_id from identity payload.

    evidence_id = "ev1:" + SHA-256(identity payload)
    Identity payload includes: identity_version, subject, target, observed_state,
    observed_value, observed_at, provenance.
    """
    identity_payload = {
        "identity_version": 1,
        "subject": subject,
        "target": target,
        "observed_state": observed_state,
        "observed_value": observed_value,
        "observed_at": observed_at,
        "provenance": provenance,
    }
    digest = sha256(_canonicalize_nextone_v1(identity_payload)).hexdigest()
    return f"ev1:{digest}"


def observer_v1_envelope_to_evidence(
    envelope_dict: dict[str, Any],
    *,
    evaluation_status: str,
    role: str | None = None,
    max_age_seconds: int = 3600,
) -> EvidenceItem:
    """Convert Observer EvidenceEnvelope v1 (JSON) to EGA EvidenceItem representation.

    This adapter handles the richer Observer v1 structure and maps it to EGA's
    internal EvidenceItem model. Observer v1 is unchanged; all transformations
    are EGA-side.

    Key transformations:
    - evidence_id: preserved exactly as Observer v1 evidence_id in evidence_ref (lossless mapping)
    - observed_state → state (exact string mapping)
    - observed_value → value (exact pass-through)
    - observed_at → observed_at (exact pass-through)
    - freshness: computed from observed_at using EGA's max_age_seconds threshold
    - target: serialized to string for correlation (e.g., "catalog:SKU1:price_cents")
    - provenance: serialized to JSON string for audit correlation
    - uncertainty.source_confidence → source_confidence (extract float)
    - integrity.digest: strip "sha256:" prefix (representation-only)

    Observer target structure is preserved as a serialized string in target field
    for evidence correlation, as the EGA EvidenceItem model does not support
    structured target fields.

    SECURITY: The adapter verifies both integrity and evidence_id before conversion:
    - Integrity: recompute canonical digest using nextone-canonical-json-v1 and reject if mismatch
    - Evidence ID: recompute from identity payload and reject if mismatch

    The Observer v1 evidence_id is preserved exactly (including "ev1:" prefix) in
    EvidenceItem.evidence_ref for lossless identity mapping.
    """
    from .models import EvidenceItem

    # Validate schema version
    schema_version = envelope_dict.get("schema_version")
    if schema_version != "nextone.observer.evidence-envelope/1.0":
        raise ValueError(
            f"Unsupported schema version: {schema_version}. "
            "Expected nextone.observer.evidence-envelope/1.0"
        )

    # Verify integrity before any conversion (security)
    if not _verify_observer_v1_integrity(envelope_dict):
        raise ValueError(
            "Observer v1 envelope integrity digest does not match canonical payload. "
            "Evidence may have been tampered with."
        )

    # Extract and validate evidence_id
    evidence_id = envelope_dict.get("evidence_id")
    if not evidence_id or not evidence_id.startswith("ev1:"):
        raise ValueError(f"Invalid evidence_id format: {evidence_id}")

    # Re-derive evidence_id from identity payload and verify consistency
    subject = envelope_dict.get("subject", {})
    target = envelope_dict.get("target", {})
    observed_state = envelope_dict.get("observed_state")
    observed_value = envelope_dict.get("observed_value")
    observed_at = envelope_dict.get("observed_at")
    provenance = envelope_dict.get("provenance", {})

    expected_evidence_id = _derive_observer_v1_evidence_id(
        subject=subject,
        target=target,
        observed_state=observed_state,
        observed_value=observed_value,
        observed_at=observed_at,
        provenance=provenance,
    )

    if evidence_id != expected_evidence_id:
        raise ValueError(
            f"Observer v1 evidence_id mismatch: supplied {evidence_id[:20]}..., "
            f"expected {expected_evidence_id[:20]}... "
            "(identity derivation failed)"
        )

    # Preserve Observer v1 evidence_id exactly in evidence_ref (lossless mapping)
    evidence_ref = evidence_id

    # Map observed_state → state
    if observed_state not in ("KNOWN", "UNKNOWN"):
        raise ValueError(f"Invalid observed_state: {observed_state}")

    # Validate UNKNOWN has null value
    if observed_state == "UNKNOWN" and observed_value is not None:
        raise ValueError("UNKNOWN state requires observed_value to be null")

    # Validate observed_at
    if not observed_at:
        raise ValueError("observed_at is required")
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")

    # Serialize target structure to string for correlation
    if isinstance(target, dict):
        target_str = f"{target.get('resource', '')}:{target.get('entity_id', '')}:{target.get('field', '')}"
    else:
        target_str = str(target)

    # Serialize provenance to JSON string for audit correlation
    provenance_str = json.dumps(provenance, sort_keys=True)

    # Extract source_confidence from uncertainty structure
    uncertainty_dict = envelope_dict.get("uncertainty", {})
    source_confidence = uncertainty_dict.get("source_confidence")
    if source_confidence is not None and not 0.0 <= source_confidence <= 1.0:
        raise ValueError("source_confidence must be between 0 and 1")

    # Extract and validate integrity digest
    integrity_dict = envelope_dict.get("integrity", {})
    integrity_digest = integrity_dict.get("digest", "")
    if not integrity_digest:
        raise ValueError("integrity.digest is required")
    if integrity_digest.startswith("sha256:"):
        integrity_digest = integrity_digest[7:]  # Strip prefix

    # Compute freshness from observed_at (EGA-side evaluation)
    freshness = _compute_freshness_from_observed_at(observed_at, max_age_seconds)

    # Build EvidenceItem
    evidence_item = EvidenceItem(
        evidence_ref=evidence_ref,
        digest=integrity_digest,
        observed_at=observed_at,
        evaluation_status=evaluation_status,
        role=role,
        target=target_str,
        state=observed_state,
        value=observed_value,
        freshness=freshness,
        uncertainty=None,  # Not used in EGA AEE predicates from Observer
        source_confidence=source_confidence,
        provenance=provenance_str,
    )

    return evidence_item
