from ega.authority import issue_authority
from ega.boundary import commit, execution_attestation, prepare
from ega.evidence import canonical_json, evidence_bundle
from ega.models import AuthorizationScope, DecisionRecord, EvidenceItem, RuntimeIntent


def make_authority():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="raig-784",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    return issue_authority(intent, scope)


def test_evidence_bundle_is_deterministic():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=1)
    eatt = execution_attestation(
        prepared, result, execution_id="exec-001", current_epoch=1
    )
    kwargs = dict(
        intent_ref="intent-001",
        authority_ref=prepared.authority.authority_id,
        prepared_context_ref="ctx-001",
        final_check_ref="check-001",
        commit_ref="commit-001",
    )
    assert canonical_json(evidence_bundle(eatt, **kwargs)) == canonical_json(
        evidence_bundle(eatt, **kwargs)
    )


def test_evidence_bundle_preserves_negative_boundary_result():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=2)
    from ega.boundary import execution_attestation

    eatt = execution_attestation(
        prepared, result, execution_id="exec-002", current_epoch=2
    )
    bundle = evidence_bundle(
        eatt,
        intent_ref="intent-002",
        authority_ref=prepared.authority.authority_id,
        prepared_context_ref="ctx-002",
        final_check_ref="check-002",
    )
    assert bundle["execution_attestation"]["decision"] == "BLOCK"
    assert bundle["execution_attestation"]["reason"] == "STALE_CONTEXT"
    assert bundle["execution_attestation"]["effect"] == "NONE"
    assert bundle["references"]["commit"] is None

def test_eatt_references_decision_record_and_selected_evidence():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=2)
    record = DecisionRecord(
        decision_id="decision-001",
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-001",
        authorization_scope_ref="scope-001",
        evidence_items=(
            EvidenceItem(
                evidence_ref="e1-human-constraint",
                digest="sha256:e1",
                observed_at="2026-09-28T09:59:00Z",
                evaluation_status="USED",
                role="commit_condition",
            ),
            EvidenceItem(
                evidence_ref="e2-stale-observation",
                digest="sha256:e2",
                observed_at="2026-09-28T09:00:00Z",
                evaluation_status="EVALUATED_NOT_USED",
                role="runtime_observation",
            ),
        ),
    )
    eatt = execution_attestation(
        prepared,
        result,
        execution_id="exec-003",
        current_epoch=2,
        decision_record=record,
        selected_evidence_refs=("e1-human-constraint",),
    )
    assert eatt.decision_record_ref == "decision-001"
    assert eatt.decision_record_digest
    assert eatt.selected_evidence_refs == ("e1-human-constraint",)
    assert eatt.reason == "STALE_CONTEXT"


def test_end_to_end_decision_record_authority_prepare_block_and_eatt():
    from ega.models import DecisionRecord, EvidenceItem

    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="decision-e2e-001",
        governance_context={"policy_refs": ["policy:process-v3"]},
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    record = DecisionRecord(
        decision_id="decision-e2e-001",
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-e2e-001",
        authorization_scope_ref="scope-e2e-001",
        evidence_items=(
            EvidenceItem(
                evidence_ref="e1-human-constraint",
                digest="sha256:e1",
                observed_at="2026-09-28T09:59:00Z",
                evaluation_status="USED",
                role="scope_constraint",
            ),
            EvidenceItem(
                evidence_ref="e2-stale-observation",
                digest="sha256:e2",
                observed_at="2026-09-28T09:00:00Z",
                evaluation_status="EVALUATED_NOT_USED",
                role="runtime_observation",
            ),
        ),
    )

    authority = issue_authority(intent, scope, decision_record=record)
    assert authority.decision_record_ref == record.decision_id
    assert authority.decision_record_digest
    assert authority.aee_conditions == ("e1-human-constraint",)

    prepared = prepare(authority, context_epoch=41)
    result = commit(
        prepared,
        current_epoch=41,
        current_evidence_digests={"e1-human-constraint": "sha256:e1-changed"},
    )
    eatt = execution_attestation(
        prepared,
        result,
        execution_id="exec-e2e-001",
        current_epoch=41,
        decision_record=record,
        selected_evidence_refs=("e1-human-constraint",),
    )

    assert result == {
        "decision": "BLOCK",
        "reason": "AEE_CONDITION_FAILED",
        "applied": False,
        "effect": "NONE",
    }
    assert eatt.decision_record_ref == record.decision_id
    assert eatt.decision_record_digest
    assert eatt.selected_evidence_refs == ("e1-human-constraint",)
    assert eatt.effect == "NONE"
