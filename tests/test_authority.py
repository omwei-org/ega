import pytest
from ega.authority import AuthorizationError, issue_authority
from ega.models import AuthorizationScope, RuntimeIntent

def make_intent(**overrides):
    values = dict(principal="agent-123", action="open", target="valve-v1", parameters={"value": 20}, environment="plant-7", decision_ref="raig-decision-784", governance_context={"policy_refs": ["policy:process-v3"]}, evidence={"provenance": "raig-system-1"})
    values.update(overrides)
    return RuntimeIntent(**values)

def make_scope(**overrides):
    values = dict(principal="agent-123", action="open", target="valve-v1", environment="plant-7", parameter_constraints={"value": {"min": 0, "max": 20}})
    values.update(overrides)
    return AuthorizationScope(**values)

def test_issue_authority_within_scope():
    authority = issue_authority(make_intent(), make_scope())
    assert authority.status == "VALID"
    assert authority.principal == "agent-123"
    assert authority.target == "valve-v1"
    assert authority.parameters["value"] == 20
    assert authority.source_decision == "raig-decision-784"
    assert authority.governance_context["policy_refs"] == ["policy:process-v3"]
    assert authority.evidence["provenance"] == "raig-system-1"

def test_out_of_scope_intent_fails_closed():
    with pytest.raises(AuthorizationError):
        issue_authority(make_intent(parameters={"value": 21}), make_scope())

def test_missing_required_input_fails_closed():
    with pytest.raises(ValueError):
        issue_authority(make_intent(target=""), make_scope())

def test_authority_does_not_execute():
    authority = issue_authority(make_intent(), make_scope())
    assert not hasattr(authority, "execute")
    assert not hasattr(authority, "commit")

def test_deterministic_issuance():
    intent, scope = make_intent(), make_scope()
    assert issue_authority(intent, scope) == issue_authority(intent, scope)


def test_issue_authority_binds_decision_record():
    from ega.models import DecisionRecord, EvidenceItem

    intent = make_intent()
    scope = make_scope()
    record = DecisionRecord(
        decision_id=intent.decision_ref,
        decision_time="2026-09-28T10:00:00Z",
        intent_ref="intent-001",
        authorization_scope_ref="scope-001",
        evidence_items=(
            EvidenceItem(
                evidence_ref="e1-human-constraint",
                digest="sha256:e1",
                observed_at="2026-09-28T09:59:00Z",
                evaluation_status="USED",
                role="scope_constraint",
            ),
        ),
    )
    authority = issue_authority(intent, scope, decision_record=record)
    assert authority.decision_record_ref == intent.decision_ref
    assert authority.decision_record_digest


def test_aee_predicate_survives_digest_change():
    from ega.models import AEECondition, DecisionRecord, EvidenceItem
    original = EvidenceItem("e1", "d1", "2026-09-30T10:00:00Z", "USED", "commit_condition",
                            target="valve-v1", state="KNOWN", freshness="FRESH", uncertainty=0.02)
    record = DecisionRecord("raig-decision-784", "2026-09-30T10:00:00Z", "intent-001", "scope-001",
                            evidence_items=(original,),
                            aee_conditions=(AEECondition("c1", "e1", "KNOWN", "FRESH", 0.10),))
    intent = make_intent()
    authority = issue_authority(intent, make_scope(), decision_record=record)
    prepared = prepare(authority, 1)
    current = EvidenceItem("e1", "d2", "2026-09-30T10:01:00Z", "USED", "commit_condition",
                           target="valve-v1", state="KNOWN", freshness="FRESH", uncertainty=0.03)
    assert final_authority_check(prepared, 1, current_evidence={"e1": current}) == "VALID"


def test_aee_predicate_blocks_when_value_no_longer_holds():
    from ega.models import AEECondition, DecisionRecord, EvidenceItem
    original = EvidenceItem("e1", "d1", "2026-09-30T10:00:00Z", "USED", "commit_condition",
                            target="valve-v1", state="KNOWN", freshness="FRESH", uncertainty=0.02)
    record = DecisionRecord("raig-decision-785", "2026-09-30T10:00:00Z", "intent-001", "scope-001",
                            evidence_items=(original,),
                            aee_conditions=(AEECondition("c1", "e1", "KNOWN", "FRESH", 0.10),))
    authority = issue_authority(make_intent(decision_ref="raig-decision-785"), make_scope(), decision_record=record)
    prepared = prepare(authority, 1)
    current = EvidenceItem("e1", "d2", "2026-09-30T10:01:00Z", "USED", "commit_condition",
                           target="valve-v1", state="KNOWN", freshness="FRESH", uncertainty=0.15)
    assert final_authority_check(prepared, 1, current_evidence={"e1": current}) == "AEE_CONDITION_FAILED:UNCERTAINTY_MAX_EXCEEDED"
