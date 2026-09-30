from ega import (
    AEECondition,
    EvidenceEnvelope,
    evidence_envelope_integrity_ref,
    evidence_envelope_to_ega,
    evaluate_aee_condition,
)


def _evidence(**overrides):
    values = {
        "schema_version": "observer-evidence/1.0",
        "evidence_id": "obs-valve-001",
        "subject": "valve-v1",
        "state": "KNOWN",
        "observed_at": "2026-09-29T14:00:00Z",
        "freshness": "FRESH",
        "temporal_basis": "source_observation_time",
        "provenance": "sensor-17",
        "value": 20,
        "uncertainty": 0.02,
    }
    values.update(overrides)
    envelope = EvidenceEnvelope(**values)
    envelope = EvidenceEnvelope(
        **{**values, "integrity_ref": evidence_envelope_integrity_ref(envelope)}
    )
    return evidence_envelope_to_ega(
        envelope, evaluation_status="EVALUATED", role=None
    )


def _condition():
    return AEECondition(
        condition_id="cond-valve-001",
        evidence_ref="obs-valve-001",
        state_equals="KNOWN",
        freshness_equals="FRESH",
        uncertainty_max=0.10,
    )


def test_predicate_holds_when_evidence_changes_but_remains_within_condition():
    original = _evidence(uncertainty=0.02)
    current = _evidence(uncertainty=0.03)

    assert original.digest != current.digest
    result = evaluate_aee_condition(_condition(), current)

    assert result.status == "VALID"
    assert result.reason == "PREDICATE_HOLDS"


def test_predicate_fails_when_uncertainty_exceeds_limit():
    current = _evidence(uncertainty=0.15)
    result = evaluate_aee_condition(_condition(), current)

    assert result.status == "FAILED"
    assert result.reason == "UNCERTAINTY_MAX_EXCEEDED"


def test_unknown_or_stale_state_fails_when_condition_requires_known_fresh():
    current = _evidence(state="UNKNOWN", freshness="STALE", uncertainty=0.03)
    result = evaluate_aee_condition(_condition(), current)

    assert result.status == "FAILED"
    assert result.reason == "STATE_MISMATCH"


def test_changed_digest_is_not_itself_a_predicate_failure():
    current = _evidence(uncertainty=0.03)
    result = evaluate_aee_condition(
        AEECondition(
            condition_id="cond-valve-002",
            evidence_ref=current.evidence_ref,
            uncertainty_max=0.10,
        ),
        current,
    )

    assert result.status == "VALID"


def test_missing_uncertainty_fails_when_uncertainty_is_required():
    current = _evidence(uncertainty=None)
    result = evaluate_aee_condition(_condition(), current)

    assert result.status == "FAILED"
    assert result.reason == "UNCERTAINTY_UNAVAILABLE"


def test_evidence_reference_mismatch_is_not_a_predicate_match():
    current = _evidence()
    result = evaluate_aee_condition(
        AEECondition(
            condition_id="cond-valve-003",
            evidence_ref="different-evidence",
            state_equals="KNOWN",
        ),
        current,
    )

    assert result.status == "FAILED"
    assert result.reason == "EVIDENCE_REF_MISMATCH"
