"""Tests for Observer EvidenceEnvelope v1 → EGA EvidenceItem adapter."""

from datetime import datetime, timezone, timedelta
from ega.interop import (
    observer_v1_envelope_to_evidence,
    _compute_freshness_from_observed_at,
    _canonicalize_nextone_v1,
    _compute_observer_v1_integrity_digest,
)
from ega.aee import evaluate_aee_condition
from ega.models import AEECondition


def _golden_observer_envelope() -> dict:
    """Golden Observer v1 envelope from reference package."""
    return {
        "schema_version": "nextone.observer.evidence-envelope/1.0",
        "evidence_id": "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320",
        "subject": {"type": "tenant", "id": "T1"},
        "target": {"resource": "catalog", "entity_id": "SKU1", "field": "price_cents"},
        "observed_state": "KNOWN",
        "observed_value": 2500,
        "observed_at": "2026-10-03T19:00:00Z",
        "temporal_basis": {
            "type": "point_in_time",
            "timestamp_semantics": "observation_completed_at",
            "clock": "UTC"
        },
        "provenance": {
            "source_id": "local-catalog",
            "source_kind": "local_catalog",
            "collection_method": "read_only",
            "source_locator": "catalog/T1/SKU1/price_cents"
        },
        "uncertainty": {
            "source_confidence": None,
            "confidence_semantics": "not_supplied"
        },
        "integrity": {
            "canonicalization": "nextone-canonical-json-v1",
            "algorithm": "sha256",
            "digest": "sha256:47b7a98f1f6f1b148e21f3dc1d462b2fea53baf1ea6f172d6bec6274c07ff193"
        }
    }


def test_golden_known_2500_successful_conversion():
    """Observer golden KNOWN/2500 → successful conversion."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(
        envelope,
        evaluation_status="USED",
        role="commit_condition",
        max_age_seconds=3600
    )

    assert evidence.evidence_ref == "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320"
    assert evidence.state == "KNOWN"
    assert evidence.value == 2500
    assert evidence.observed_at == "2026-10-03T19:00:00Z"
    assert evidence.target == "catalog:SKU1:price_cents"
    assert evidence.digest == "47b7a98f1f6f1b148e21f3dc1d462b2fea53baf1ea6f172d6bec6274c07ff193"
    assert evidence.source_confidence is None
    # evidence_ref preserves Observer evidence_id exactly (including ev1: prefix)
    assert evidence.evidence_ref == envelope["evidence_id"]
    # role is preserved as-is, not polluted with Observer identity
    assert evidence.role == "commit_condition"


def test_unknown_successful_conversion_with_value_none():
    """Observer UNKNOWN → successful conversion with value=None."""
    from hashlib import sha256
    from ega.interop import _canonicalize_nextone_v1

    envelope = _golden_observer_envelope()
    envelope["observed_state"] = "UNKNOWN"
    envelope["observed_value"] = None

    # Re-compute correct evidence_id for the modified envelope
    identity_payload = {
        "identity_version": 1,
        "subject": envelope["subject"],
        "target": envelope["target"],
        "observed_state": envelope["observed_state"],
        "observed_value": envelope["observed_value"],
        "observed_at": envelope["observed_at"],
        "provenance": envelope["provenance"],
    }
    digest = sha256(_canonicalize_nextone_v1(identity_payload)).hexdigest()
    envelope["evidence_id"] = f"ev1:{digest}"

    # Re-compute correct integrity digest for the modified envelope
    from ega.interop import _compute_observer_v1_integrity_digest
    envelope["integrity"]["digest"] = _compute_observer_v1_integrity_digest(envelope)

    evidence = observer_v1_envelope_to_evidence(
        envelope,
        evaluation_status="EVALUATED",
        role=None
    )

    assert evidence.state == "UNKNOWN"
    assert evidence.value is None
    assert evidence.evidence_ref == f"ev1:{digest}"
    assert evidence.role is None


def test_freshness_derived_from_observed_at():
    """Freshness derived from observed_at at EGA evaluation time."""
    # Recent observation should be FRESH
    recent_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    freshness = _compute_freshness_from_observed_at(recent_time, max_age_seconds=3600)
    assert freshness == "FRESH"

    # Old observation should be STALE
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    freshness = _compute_freshness_from_observed_at(old_time, max_age_seconds=3600)
    assert freshness == "STALE"


def test_fresh_boundary_exactly_at_threshold():
    """Freshness boundary exactly at threshold."""
    # Exactly at threshold should be FRESH (with small tolerance for execution time)
    boundary_time = (datetime.now(timezone.utc) - timedelta(seconds=3599)).strftime("%Y-%m-%dT%H:%M:%SZ")
    freshness = _compute_freshness_from_observed_at(boundary_time, max_age_seconds=3600)
    assert freshness == "FRESH"

    # One second over threshold should be STALE
    boundary_time = (datetime.now(timezone.utc) - timedelta(seconds=3601)).strftime("%Y-%m-%dT%H:%M:%SZ")
    freshness = _compute_freshness_from_observed_at(boundary_time, max_age_seconds=3600)
    assert freshness == "STALE"


def test_conflicting_observations_remain_separate():
    """Conflicting Observer envelopes remain separate through adapter."""
    from hashlib import sha256

    envelope_a = _golden_observer_envelope()
    envelope_a["observed_value"] = 2500

    # Re-compute correct evidence_id and integrity for envelope_a
    identity_payload_a = {
        "identity_version": 1,
        "subject": envelope_a["subject"],
        "target": envelope_a["target"],
        "observed_state": envelope_a["observed_state"],
        "observed_value": envelope_a["observed_value"],
        "observed_at": envelope_a["observed_at"],
        "provenance": envelope_a["provenance"],
    }
    digest_a = sha256(_canonicalize_nextone_v1(identity_payload_a)).hexdigest()
    envelope_a["evidence_id"] = f"ev1:{digest_a}"
    envelope_a["integrity"]["digest"] = _compute_observer_v1_integrity_digest(envelope_a)

    envelope_b = _golden_observer_envelope()
    envelope_b["observed_value"] = 2600

    # Re-compute correct evidence_id and integrity for envelope_b
    identity_payload_b = {
        "identity_version": 1,
        "subject": envelope_b["subject"],
        "target": envelope_b["target"],
        "observed_state": envelope_b["observed_state"],
        "observed_value": envelope_b["observed_value"],
        "observed_at": envelope_b["observed_at"],
        "provenance": envelope_b["provenance"],
    }
    digest_b = sha256(_canonicalize_nextone_v1(identity_payload_b)).hexdigest()
    envelope_b["evidence_id"] = f"ev1:{digest_b}"
    envelope_b["integrity"]["digest"] = _compute_observer_v1_integrity_digest(envelope_b)

    evidence_a = observer_v1_envelope_to_evidence(envelope_a, evaluation_status="USED")
    evidence_b = observer_v1_envelope_to_evidence(envelope_b, evaluation_status="USED")

    assert evidence_a.evidence_ref != evidence_b.evidence_ref
    assert evidence_a.value == 2500
    assert evidence_b.value == 2600
    # evidence_ref preserves Observer evidence_id exactly
    assert evidence_a.evidence_ref == envelope_a["evidence_id"]
    assert evidence_b.evidence_ref == envelope_b["evidence_id"]


def test_integrity_tampering_rejected():
    """Integrity tampering is rejected (real behavioral test)."""
    envelope = _golden_observer_envelope()
    # Mutate a protected field but keep the original digest
    envelope["observed_value"] = 9999  # Tampered value
    # Keep original digest (will not match tampered payload)

    try:
        observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")
        assert False, "Should reject tampered envelope with mismatched integrity"
    except ValueError as exc:
        assert "integrity digest does not match" in str(exc)


def test_evidence_identity_mismatch_rejected():
    """Evidence identity mismatch is rejected (real behavioral test)."""
    envelope = _golden_observer_envelope()
    # Mutate a field that affects evidence_id derivation
    envelope["subject"] = {"type": "tenant", "id": "T2"}  # Changed from T1

    # Re-compute integrity digest so integrity check passes
    envelope["integrity"]["digest"] = _compute_observer_v1_integrity_digest(envelope)

    # Keep original evidence_id (will not match derived from new subject)
    # Original evidence_id was derived from subject.id="T1", but now it's "T2"

    try:
        observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")
        assert False, "Should reject envelope with mismatched evidence_id"
    except ValueError as exc:
        assert "evidence_id mismatch" in str(exc)


def test_unknown_with_non_null_value_rejected():
    """UNKNOWN state with non-null value is rejected."""
    from hashlib import sha256

    envelope = _golden_observer_envelope()
    envelope["observed_state"] = "UNKNOWN"
    envelope["observed_value"] = 2500  # Should be null

    # Re-compute correct evidence_id and integrity for the modified envelope
    identity_payload = {
        "identity_version": 1,
        "subject": envelope["subject"],
        "target": envelope["target"],
        "observed_state": envelope["observed_state"],
        "observed_value": envelope["observed_value"],
        "observed_at": envelope["observed_at"],
        "provenance": envelope["provenance"],
    }
    digest = sha256(_canonicalize_nextone_v1(identity_payload)).hexdigest()
    envelope["evidence_id"] = f"ev1:{digest}"
    envelope["integrity"]["digest"] = _compute_observer_v1_integrity_digest(envelope)

    try:
        observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")
        assert False, "Should reject UNKNOWN with non-null value"
    except ValueError as exc:
        assert "UNKNOWN state requires observed_value to be null" in str(exc)


def test_schema_version_mismatch_rejected():
    """Wrong schema version is rejected."""
    envelope = _golden_observer_envelope()
    envelope["schema_version"] = "wrong-version"

    try:
        observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")
        assert False, "Should reject wrong schema version"
    except ValueError as exc:
        assert "Unsupported schema version" in str(exc)


def test_target_serialization_preserves_structure():
    """Target structure is serialized to string for correlation."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")

    # Target should be serialized as "resource:entity_id:field"
    assert evidence.target == "catalog:SKU1:price_cents"


def test_provenance_serialization_preserves_identity():
    """Provenance is serialized to JSON for audit correlation."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")

    # Provenance should be serialized JSON
    import json
    provenance = json.loads(evidence.provenance)
    assert provenance["source_id"] == "local-catalog"
    assert provenance["source_kind"] == "local_catalog"
    assert provenance["collection_method"] == "read_only"


def test_integrity_prefix_stripped():
    """Integrity digest prefix is stripped (representation-only)."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")

    # Should strip "sha256:" prefix
    assert not evidence.digest.startswith("sha256:")
    assert evidence.digest == "47b7a98f1f6f1b148e21f3dc1d462b2fea53baf1ea6f172d6bec6274c07ff193"


def test_evidence_id_prefix_preserved():
    """Evidence ID prefix is preserved exactly in evidence_ref (lossless mapping)."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")

    # Should preserve "ev1:" prefix in evidence_ref
    assert evidence.evidence_ref.startswith("ev1:")
    # evidence_ref equals Observer evidence_id exactly
    assert evidence.evidence_ref == envelope["evidence_id"]


def test_aee_value_equals_2500_succeeds_with_golden_evidence():
    """AEE value_equals=2500 succeeds with golden evidence."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(
        envelope,
        evaluation_status="USED",
        role="commit_condition"
    )

    condition = AEECondition(
        condition_id="c-price-2500",
        evidence_ref=evidence.evidence_ref,  # Uses Observer evidence_id with ev1: prefix
        state_equals="KNOWN",
        value_equals=2500,
    )

    eval_result = evaluate_aee_condition(condition, evidence)
    assert eval_result.status == "VALID"
    assert eval_result.reason == "PREDICATE_HOLDS"


def test_aee_value_equals_2600_fails_with_golden_evidence():
    """AEE value_equals=2600 fails with golden evidence (value is 2500)."""
    envelope = _golden_observer_envelope()
    evidence = observer_v1_envelope_to_evidence(
        envelope,
        evaluation_status="USED",
        role="commit_condition"
    )

    condition = AEECondition(
        condition_id="c-price-2600",
        evidence_ref=evidence.evidence_ref,
        state_equals="KNOWN",
        value_equals=2600,
    )

    eval_result = evaluate_aee_condition(condition, evidence)
    assert eval_result.status == "FAILED"
    assert eval_result.reason == "VALUE_MISMATCH"
