from ega.authority import issue_authority
from ega.boundary import commit, execution_attestation, prepare
from ega.evidence import canonical_json, evidence_bundle
from ega.models import AEECondition, AuthorizationScope, DecisionRecord, EvidenceItem, RuntimeIntent


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
    record = DecisionRecord(
        decision_id="raig-784",
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
    authority = issue_authority(intent, scope, decision_record=record)
    prepared = prepare(authority, context_epoch=1)
    result = commit(prepared, current_epoch=2)
    eatt = execution_attestation(
        prepared,
        result,
        execution_id="exec-003",
        current_epoch=2,
        decision_record=record,
        selected_evidence_refs=("e1-human-constraint",),
    )
    assert eatt.decision_record_ref == "raig-784"
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

    authority = issue_authority(intent, scope, decision_record=record)
    assert authority.decision_record_ref == record.decision_id
    assert authority.decision_record_digest
    assert authority.aee_conditions == record.aee_conditions

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

def test_issuance_evidence_is_not_automatically_promoted_to_aee_condition():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="decision-separation-001",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    record = DecisionRecord(
        decision_id="decision-separation-001",
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-separation-001",
        authorization_scope_ref="scope-separation-001",
        evidence_items=(
            EvidenceItem(
                evidence_ref="e-issuance",
                digest="sha256:issuance",
                observed_at="2026-09-28T09:59:00Z",
                evaluation_status="USED",
                role="issuance_basis",
            ),
            EvidenceItem(
                evidence_ref="e-observation",
                digest="sha256:observation",
                observed_at="2026-09-28T09:59:30Z",
                evaluation_status="EVALUATED_NOT_USED",
                role="runtime_observation",
            ),
        ),
    )

    authority = issue_authority(intent, scope, decision_record=record)

    assert authority.decision_record_ref == record.decision_id
    assert authority.aee_conditions == ()



def test_unchanged_aee_condition_allows_commit():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="decision-positive-001",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    record = DecisionRecord(
        decision_id="decision-positive-001",
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-positive-001",
        authorization_scope_ref="scope-positive-001",
        evidence_items=(
            EvidenceItem(
                evidence_ref="e1-human-constraint",
                digest="sha256:e1",
                observed_at="2026-09-28T09:59:00Z",
                evaluation_status="USED",
                role="commit_condition",
                state="KNOWN",
            ),
        ),
        aee_conditions=(AEECondition("c1", "e1-human-constraint", state_equals="KNOWN"),),
    )

    authority = issue_authority(intent, scope, decision_record=record)
    prepared = prepare(authority, context_epoch=41)
    result = commit(
        prepared,
        current_epoch=41,
        current_evidence={"e1-human-constraint": EvidenceItem("e1-human-constraint", "sha256:e1", "2026-09-28T10:00:00Z", "USED", "commit_condition", state="KNOWN")},
    )

    assert result == {
        "decision": "COMMIT",
        "reason": "VALID",
        "applied": True,
        "effect": "NOT_EXECUTED",
    }

def test_eatt_rejects_mismatched_decision_record():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="decision-bound-001",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    bound_record = DecisionRecord(
        decision_id="decision-bound-001",
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-bound-001",
        authorization_scope_ref="scope-bound-001",
    )
    other_record = DecisionRecord(
        decision_id="decision-other-001",
        decision_time="2026-09-28T10:01:00Z",
        intent_ref="intent-other-001",
        authorization_scope_ref="scope-other-001",
    )
    authority = issue_authority(intent, scope, decision_record=bound_record)
    prepared = prepare(authority, context_epoch=41)
    result = commit(prepared, current_epoch=41)

    import pytest
    with pytest.raises(ValueError, match="does not match prepared authority"):
        execution_attestation(
            prepared,
            result,
            execution_id="exec-boundary-001",
            current_epoch=41,
            decision_record=other_record,
        )


def test_eatt_rejects_unlisted_selected_evidence():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="decision-evidence-001",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    record = DecisionRecord(
        decision_id="decision-evidence-001",
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-evidence-001",
        authorization_scope_ref="scope-evidence-001",
        evidence_items=(
            EvidenceItem(
                evidence_ref="e1",
                digest="sha256:e1",
                observed_at="2026-09-28T09:59:00Z",
                evaluation_status="USED",
                role="commit_condition",
            ),
        ),
    )
    authority = issue_authority(intent, scope, decision_record=record)
    prepared = prepare(authority, context_epoch=41)
    result = commit(prepared, current_epoch=41)

    import pytest
    with pytest.raises(ValueError, match="not present in decision record"):
        execution_attestation(
            prepared,
            result,
            execution_id="exec-evidence-001",
            current_epoch=41,
            decision_record=record,
            selected_evidence_refs=("e999",),
        )

def test_evidence_bundle_rejects_mismatched_authority_ref():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=1)
    eatt = execution_attestation(
        prepared, result, execution_id="exec-bundle-001", current_epoch=1
    )
    import pytest
    with pytest.raises(ValueError, match="authority reference does not match"):
        evidence_bundle(
            eatt,
            intent_ref="intent-001",
            authority_ref="wrong-authority",
            prepared_context_ref="ctx-001",
            final_check_ref="check-001",
            commit_ref="commit-001",
        )


def test_evidence_bundle_requires_commit_ref_for_commit():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=1)
    eatt = execution_attestation(
        prepared, result, execution_id="exec-bundle-002", current_epoch=1
    )
    import pytest
    with pytest.raises(ValueError, match="commit_ref is required"):
        evidence_bundle(
            eatt,
            intent_ref="intent-001",
            authority_ref=prepared.authority.authority_id,
            prepared_context_ref="ctx-001",
            final_check_ref="check-001",
        )


def test_evidence_bundle_rejects_missing_required_correlation_ref():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=1)
    eatt = execution_attestation(
        prepared, result, execution_id="exec-bundle-003", current_epoch=1
    )
    import pytest
    with pytest.raises(ValueError, match="final_check_ref is required"):
        evidence_bundle(
            eatt,
            intent_ref="intent-001",
            authority_ref=prepared.authority.authority_id,
            prepared_context_ref="ctx-001",
            final_check_ref="",
            commit_ref="commit-001",
        )


def test_evidence_bundle_accepts_complete_commit_correlation():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=1)
    eatt = execution_attestation(
        prepared, result, execution_id="exec-bundle-004", current_epoch=1
    )
    bundle = evidence_bundle(
        eatt,
        intent_ref="intent-001",
        authority_ref=prepared.authority.authority_id,
        prepared_context_ref="ctx-001",
        final_check_ref="check-001",
        commit_ref="commit-001",
    )
    assert bundle["references"]["authority"] == prepared.authority.authority_id
    assert bundle["references"]["commit"] == "commit-001"
    assert bundle["manifest_sha256"]
