from ega.authority import issue_authority
from ega.boundary import commit, execution_attestation, final_authority_check, prepare
from ega.models import AEECondition, AuthorizationScope, DecisionRecord, EvidenceItem, RuntimeIntent

def authority():
    intent = RuntimeIntent(principal="agent-123", action="open", target="valve-v1", parameters={"value": 20}, environment="plant-7", decision_ref="raig-784")
    scope = AuthorizationScope(principal="agent-123", action="open", target="valve-v1", environment="plant-7", parameter_constraints={"value": {"min": 0, "max": 20}})
    return issue_authority(intent, scope)

def test_prepare_then_commit():
    prepared = prepare(authority(), context_epoch=1)
    assert final_authority_check(prepared, current_epoch=1) == "VALID"
    assert commit(prepared, current_epoch=1) == {"decision": "COMMIT", "reason": "VALID", "applied": True, "effect": "NOT_EXECUTED"}

def test_epoch_change_blocks_commit():
    prepared = prepare(authority(), context_epoch=1)
    assert final_authority_check(prepared, current_epoch=2) == "STALE_CONTEXT"
    assert commit(prepared, current_epoch=2) == {"decision": "BLOCK", "reason": "STALE_CONTEXT", "applied": False, "effect": "NONE"}

def test_authority_change_blocks_commit():
    original = authority()
    prepared = prepare(original, context_epoch=1)
    changed = type(original)(**{**original.__dict__, "parameters": {"value": 19}})
    assert final_authority_check(prepared, current_epoch=1, current_authority=changed) == "AUTHORITY_DIGEST_MISMATCH"


def test_execution_attestation_binds_blocked_attempt():
    prepared = prepare(authority(), context_epoch=1)
    result = commit(prepared, current_epoch=2)
    eatt = execution_attestation(prepared, result, execution_id="exec-001", current_epoch=2)
    assert eatt.authority_id == prepared.authority.authority_id
    assert eatt.authority_digest == prepared.authority_digest
    assert eatt.prepared_context_epoch == 1
    assert eatt.current_context_epoch == 2
    assert eatt.decision == "BLOCK"
    assert eatt.reason == "STALE_CONTEXT"
    assert eatt.commit == "NOT_ATTEMPTED"
    assert eatt.effect == "NONE"


def test_execution_attestation_preserves_eabc_lineage():
    base = authority()
    authority_with_lineage = type(base)(**{**base.__dict__, "ao_ref": "ao-001", "aee_ref": "aee-001", "ect_ref": "ect-001"})
    prepared = prepare(authority_with_lineage, context_epoch=1)
    result = commit(prepared, current_epoch=2)
    eatt = execution_attestation(prepared, result, execution_id="exec-002", current_epoch=2)
    assert (eatt.ao_ref, eatt.aee_ref, eatt.ect_ref) == ("ao-001", "aee-001", "ect-001")


def _price_authority():
    intent = RuntimeIntent(
        principal="agent-123",
        action="retail_sale",
        target="orders",
        parameters={"tenant_id": "T1", "sku": "SKU1", "qty": 1},
        environment="comos-local",
        decision_ref="decision-price-001",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="retail_sale",
        target="orders",
        environment="comos-local",
        parameter_constraints={"tenant_id": "T1", "sku": "SKU1"},
    )
    evidence = EvidenceItem(
        evidence_ref="obs-catalog-001",
        digest="D1",
        observed_at="2026-10-03T07:00:00Z",
        evaluation_status="USED",
        role="commit_condition",
        target="catalog:T1:SKU1",
        state="KNOWN",
        value={"tenant_id": "T1", "sku": "SKU1", "price_cents": 2500},
        freshness="FRESH",
        uncertainty=0.01,
        provenance="observer-local",
    )
    record = DecisionRecord(
        decision_id="decision-price-001",
        decision_time="2026-10-03T07:00:01Z",
        intent_ref="intent-price-001",
        authorization_scope_ref="ao-comos-price-001",
        evidence_items=(evidence,),
        aee_conditions=(
            AEECondition(
                condition_id="condition-price-001",
                evidence_ref="obs-catalog-001",
                value_equals={
                    "tenant_id": "T1",
                    "sku": "SKU1",
                    "price_cents": 2500,
                },
            ),
        ),
    )
    return issue_authority(intent, scope, decision_record=record), record


def test_comos_catalog_value_predicate_allows_commit():
    authority, record = _price_authority()
    prepared = prepare(authority, context_epoch=1)

    current = EvidenceItem(
        evidence_ref="obs-catalog-001",
        digest="D2",
        observed_at="2026-10-03T07:00:02Z",
        evaluation_status="USED",
        role="commit_condition",
        target="catalog:T1:SKU1",
        state="KNOWN",
        value={"tenant_id": "T1", "sku": "SKU1", "price_cents": 2500},
        freshness="FRESH",
        uncertainty=0.01,
        provenance="observer-local",
    )

    assert final_authority_check(
        prepared,
        current_epoch=1,
        current_evidence={"obs-catalog-001": current},
    ) == "VALID"

    result = commit(
        prepared,
        current_epoch=1,
        current_evidence={"obs-catalog-001": current},
    )
    assert result == {
        "decision": "COMMIT",
        "reason": "VALID",
        "applied": True,
        "effect": "NOT_EXECUTED",
    }

    eatt = execution_attestation(
        prepared,
        result,
        execution_id="exec-price-001",
        current_epoch=1,
        decision_record=record,
        selected_evidence_refs=("obs-catalog-001",),
    )
    assert eatt.decision_record_ref == "decision-price-001"
    assert eatt.selected_evidence_refs == ("obs-catalog-001",)


def test_comos_catalog_value_predicate_blocks_on_price_change():
    authority, _ = _price_authority()
    prepared = prepare(authority, context_epoch=1)

    current = EvidenceItem(
        evidence_ref="obs-catalog-001",
        digest="D3",
        observed_at="2026-10-03T07:00:02Z",
        evaluation_status="USED",
        role="commit_condition",
        target="catalog:T1:SKU1",
        state="KNOWN",
        value={"tenant_id": "T1", "sku": "SKU1", "price_cents": 2600},
        freshness="FRESH",
        uncertainty=0.01,
        provenance="observer-local",
    )

    assert final_authority_check(
        prepared,
        current_epoch=1,
        current_evidence={"obs-catalog-001": current},
    ) == "AEE_CONDITION_FAILED:VALUE_MISMATCH"

    assert commit(
        prepared,
        current_epoch=1,
        current_evidence={"obs-catalog-001": current},
    ) == {
        "decision": "BLOCK",
        "reason": "AEE_CONDITION_FAILED:VALUE_MISMATCH",
        "applied": False,
        "effect": "NONE",
    }
