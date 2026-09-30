from ega import EvidenceEnvelope, evidence_envelope_integrity_ref, evidence_envelope_to_ega


def _envelope(**overrides):
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
    return EvidenceEnvelope(
        **{**values, "integrity_ref": evidence_envelope_integrity_ref(envelope)}
    )


def test_contract_has_integrity_over_canonical_evidence_payload():
    envelope = _envelope()
    assert envelope.integrity_ref == evidence_envelope_integrity_ref(envelope)


def test_contract_adapter_preserves_evidence_without_assigning_materiality():
    envelope = _envelope()
    evidence = evidence_envelope_to_ega(
        envelope, evaluation_status="EVALUATED", role=None
    )

    assert evidence.evidence_ref == envelope.evidence_id
    assert evidence.target == envelope.subject
    assert evidence.state == envelope.state
    assert evidence.value == envelope.value
    assert evidence.observed_at == envelope.observed_at
    assert evidence.freshness == envelope.freshness
    assert evidence.uncertainty == envelope.uncertainty
    assert evidence.provenance == envelope.provenance
    assert evidence.digest == envelope.integrity_ref
    assert evidence.role is None


def test_contract_rejects_tampered_payload():
    envelope = _envelope()
    tampered = EvidenceEnvelope(
        **{
            **envelope.__dict__,
            "uncertainty": 0.03,
        }
    )

    try:
        evidence_envelope_to_ega(
            tampered, evaluation_status="EVALUATED", role=None
        )
    except ValueError as exc:
        assert "integrity_ref" in str(exc)
    else:
        raise AssertionError("tampered evidence envelope must be rejected")


def test_unknown_is_explicit_evidence_state_not_an_authority_decision():
    envelope = _envelope(state="UNKNOWN", freshness="STALE")
    evidence = evidence_envelope_to_ega(
        envelope, evaluation_status="EVALUATED", role=None
    )
    assert evidence.state == "UNKNOWN"
    assert evidence.freshness == "STALE"
    assert evidence.role is None
