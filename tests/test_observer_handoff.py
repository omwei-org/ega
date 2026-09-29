from ega import (
    AuthorizationScope,
    DecisionRecord,
    EvidenceItem,
    ExecutionAttestation,
    ObserverObservation,
    RuntimeIntent,
    commit,
    execution_attestation,
    final_authority_check,
    issue_authority,
    observation_to_evidence,
    prepare,
)
from ega.evidence import decision_record_digest


def _observation(*, freshness="FRESH", state="KNOWN", uncertainty=0.02, digest="obs-digest-1"):
    return ObserverObservation(
        observation_ref="obs-valve-001",
        target="valve-v1",
        observed_at="2026-09-29T14:00:00Z",
        state=state,
        value=20,
        freshness=freshness,
        uncertainty=uncertainty,
        provenance="sensor-17",
        digest=digest,
    )


def _authority(evidence_item):
    record = DecisionRecord(
        decision_id="decision-001",
        decision_time="2026-09-29T14:00:01Z",
        intent_ref="intent-001",
        authorization_scope_ref="scope-001",
        evidence_items=(evidence_item,),
    )
    intent = RuntimeIntent(
        principal="agent-123",
        action="set",
        target="valve-v1",
        parameters={"position": 20},
        environment="production",
        decision_ref=record.decision_id,
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="set",
        target="valve-v1",
        environment="production",
    )
    authority = issue_authority(intent, scope, decision_record=record)
    return authority, record


def test_observer_handoff_preserves_runtime_metadata_and_issuance_lineage():
    evidence = observation_to_evidence(
        _observation(), evaluation_status="USED", role="issuance_basis"
    )
    assert evidence.evidence_ref == "obs-valve-001"
    assert evidence.state == "KNOWN"
    assert evidence.freshness == "FRESH"
    assert evidence.uncertainty == 0.02
    assert evidence.provenance == "sensor-17"

    authority, record = _authority(evidence)
    assert authority.aee_conditions == ()
    assert authority.decision_record_ref == record.decision_id
    assert authority.decision_record_digest == decision_record_digest(record)


def test_fresh_known_observation_promoted_to_commit_condition_can_commit():
    evidence = observation_to_evidence(
        _observation(), evaluation_status="USED", role="commit_condition"
    )
    authority, _ = _authority(evidence)
    prepared = prepare(authority)

    check = final_authority_check(
        prepared,
        current_epoch=prepared.context_epoch,
        current_evidence_digests={"obs-valve-001": "obs-digest-1"},
    )
    assert check == "VALID"
    assert commit(prepared, check)["decision"] == "COMMIT"


def test_stale_observation_fails_commit_condition():
    evidence = observation_to_evidence(
        _observation(), evaluation_status="USED", role="commit_condition"
    )
    authority, _ = _authority(evidence)
    prepared = prepare(authority)

    check = final_authority_check(
        prepared,
        current_epoch=prepared.context_epoch,
        current_evidence_digests={"obs-valve-001": "obs-digest-stale"},
    )
    assert check == "AEE_CONDITION_FAILED"
    assert commit(prepared, check)["decision"] == "BLOCK"


def test_unknown_observation_fails_when_the_required_observation_changes():
    evidence = observation_to_evidence(
        _observation(), evaluation_status="USED", role="commit_condition"
    )
    authority, _ = _authority(evidence)
    prepared = prepare(authority)

    unknown = _observation(state="UNKNOWN", digest="obs-digest-unknown")
    current_evidence = observation_to_evidence(
        unknown, evaluation_status="USED", role="commit_condition"
    )
    assert current_evidence.state == "UNKNOWN"

    check = final_authority_check(
        prepared,
        current_epoch=prepared.context_epoch,
        current_evidence_digests={"obs-valve-001": current_evidence.digest},
    )
    assert check == "AEE_CONDITION_FAILED"


def test_uncertainty_change_fails_only_when_uncertainty_is_part_of_commit_evidence():
    issuance_only = observation_to_evidence(
        _observation(), evaluation_status="USED", role="issuance_basis"
    )
    authority, _ = _authority(issuance_only)
    prepared = prepare(authority)

    # Uncertainty may change without becoming an AEE condition because the
    # observation was retained only as issuance evidence.
    changed = _observation(uncertainty=0.9, digest="obs-digest-uncertain")
    current = observation_to_evidence(
        changed, evaluation_status="USED", role="issuance_basis"
    )
    check = final_authority_check(
        prepared,
        current_epoch=prepared.context_epoch,
        current_evidence_digests={"obs-valve-001": current.digest},
    )
    assert check == "VALID"


def test_execution_attestation_reconstructs_observer_lineage():
    evidence = observation_to_evidence(
        _observation(), evaluation_status="USED", role="commit_condition"
    )
    authority, record = _authority(evidence)
    prepared = prepare(authority)
    check = final_authority_check(
        prepared,
        current_epoch=prepared.context_epoch,
        current_evidence_digests={"obs-valve-001": "obs-digest-1"},
    )
    result = commit(prepared, check)
    eatt = execution_attestation(
        prepared,
        current_epoch=prepared.context_epoch,
        decision=result["decision"],
        reason=result["reason"],
        commit=result["decision"],
        effect=result["effect"],
        decision_record=record,
        selected_evidence_refs=("obs-valve-001",),
    )
    assert eatt.decision_record_ref == record.decision_id
    assert eatt.selected_evidence_refs == ("obs-valve-001",)
