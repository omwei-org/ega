from ega.aee import evaluate_aee_condition
from ega.authority import issue_authority
from ega.boundary import commit, execution_attestation, prepare
from ega.interop import EvidenceEnvelope, evidence_envelope_integrity_ref, evidence_envelope_to_evidence
from ega.models import AEECondition, AuthorizationScope, DecisionRecord, RuntimeIntent


def make_intent(decision_ref="raig-e2e-001"):
    return RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref=decision_ref,
        governance_context={"policy_refs": ["policy:process-v3"]},
    )


def make_scope():
    return AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )


def make_envelope(*, evidence_id, observed_at, state, freshness, uncertainty):
    envelope = EvidenceEnvelope(
        schema_version="1.0",
        evidence_id=evidence_id,
        subject="valve-v1",
        state=state,
        observed_at=observed_at,
        freshness=freshness,
        temporal_basis="observer-clock",
        provenance="observer-1",
        uncertainty=uncertainty,
        integrity_ref="",
    )
    return EvidenceEnvelope(
        **{**envelope.__dict__, "integrity_ref": evidence_envelope_integrity_ref(envelope)}
    )


def test_observer_to_commit_end_to_end():
    # T0: Observer evidence is accepted by EGA and projected into an AEE condition.
    t0 = make_envelope(
        evidence_id="obs-001",
        observed_at="2026-09-30T10:00:00Z",
        state="KNOWN",
        freshness="FRESH",
        uncertainty=0.02,
    )
    t0_evidence = evidence_envelope_to_evidence(
        t0, evaluation_status="USED", role="commit_condition"
    )
    condition = AEECondition(
        condition_id="c-known-fresh",
        evidence_ref="obs-001",
        state_equals="KNOWN",
        freshness_equals="FRESH",
        uncertainty_max=0.10,
    )
    record = DecisionRecord(
        decision_id="raig-e2e-001",
        decision_time="2026-09-30T10:00:00Z",
        intent_ref="intent-e2e-001",
        authorization_scope_ref="scope-e2e-001",
        evidence_items=(t0_evidence,),
        aee_conditions=(condition,),
    )

    authority = issue_authority(
        make_intent(),
        make_scope(),
        decision_record=record,
    )
    prepared = prepare(authority, context_epoch=1)

    # T1: evidence digest changes, but the declared predicate still holds.
    t1 = make_envelope(
        evidence_id="obs-001",
        observed_at="2026-09-30T10:01:00Z",
        state="KNOWN",
        freshness="FRESH",
        uncertainty=0.03,
    )
    t1_evidence = evidence_envelope_to_evidence(
        t1, evaluation_status="USED", role="commit_condition"
    )
    assert t1.integrity_ref != t0.integrity_ref
    assert evaluate_aee_condition(condition, t1_evidence).status == "VALID"

    committed = commit(
        prepared,
        current_epoch=1,
        current_evidence={"obs-001": t1_evidence},
    )
    assert committed == {
        "decision": "COMMIT",
        "reason": "VALID",
        "applied": True,
        "effect": "NOT_EXECUTED",
    }

    attestation = execution_attestation(
        prepared,
        committed,
        execution_id="exec-e2e-commit",
        current_epoch=1,
        decision_record=record,
        selected_evidence_refs=("obs-001",),
    )
    assert attestation.decision == "COMMIT"
    assert attestation.commit == "ATTEMPTED"
    assert attestation.effect == "NOT_EXECUTED"
    assert attestation.decision_record_ref == record.decision_id
    assert attestation.selected_evidence_refs == ("obs-001",)

    # T1 failure: the same authority is blocked when the declared condition no longer holds.
    t1_failed = make_envelope(
        evidence_id="obs-001",
        observed_at="2026-09-30T10:02:00Z",
        state="KNOWN",
        freshness="FRESH",
        uncertainty=0.15,
    )
    t1_failed_evidence = evidence_envelope_to_evidence(
        t1_failed, evaluation_status="USED", role="commit_condition"
    )
    blocked = commit(
        prepared,
        current_epoch=1,
        current_evidence={"obs-001": t1_failed_evidence},
    )
    assert blocked == {
        "decision": "BLOCK",
        "reason": "AEE_CONDITION_FAILED:UNCERTAINTY_MAX_EXCEEDED",
        "applied": False,
        "effect": "NONE",
    }

    blocked_attestation = execution_attestation(
        prepared,
        blocked,
        execution_id="exec-e2e-block",
        current_epoch=1,
        decision_record=record,
        selected_evidence_refs=("obs-001",),
    )
    assert blocked_attestation.decision == "BLOCK"
    assert blocked_attestation.commit == "NOT_ATTEMPTED"
    assert blocked_attestation.effect == "NONE"
