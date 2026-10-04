"""End-to-end tests for Observer v1 → EGA → AEE → authority decision flow.

These tests verify the complete production path:
Observer v1 envelope → observer_v1_envelope_to_evidence → EvidenceItem
→ DecisionRecord → ExecutionAuthority → prepare → final_authority_check → commit

This uses existing EGA production functions without any architecture changes.
"""

from datetime import datetime, timezone, timedelta
from hashlib import sha256

from ega.authority import issue_authority
from ega.boundary import commit, final_authority_check, prepare
from ega.interop import (
    observer_v1_envelope_to_evidence,
    _canonicalize_nextone_v1,
    _compute_observer_v1_integrity_digest,
)
from ega.models import (
    AEECondition,
    AuthorizationScope,
    DecisionRecord,
    EvidenceItem,
    RuntimeIntent,
)


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


def _make_price_authority_with_observer_v1(
    observer_envelope: dict,
    aee_value_equals: int,
) -> tuple[dict, EvidenceItem, DecisionRecord]:
    """Create EGA authority flow with Observer v1 evidence and AEE condition.

    Returns:
        (authority, evidence_item, decision_record)
    """
    # Step 1: Convert Observer v1 envelope to EGA EvidenceItem
    evidence_item = observer_v1_envelope_to_evidence(
        observer_envelope,
        evaluation_status="USED",
        role="commit_condition",
        max_age_seconds=3600,
    )

    # Step 2: Create AEE condition using Observer evidence_id
    aee_condition = AEECondition(
        condition_id="condition-price-observer-v1",
        evidence_ref=observer_envelope["evidence_id"],  # Uses ev1: prefix
        state_equals="KNOWN",
        value_equals=aee_value_equals,
    )

    # Step 3: Create DecisionRecord with evidence and AEE condition
    decision_record = DecisionRecord(
        decision_id="decision-observer-v1-001",
        decision_time="2026-10-03T19:00:01Z",
        intent_ref="intent-observer-v1-001",
        authorization_scope_ref="scope-observer-v1-001",
        evidence_items=(evidence_item,),
        aee_conditions=(aee_condition,),
    )

    # Step 4: Create runtime intent and authorization scope
    intent = RuntimeIntent(
        principal="agent-123",
        action="retail_sale",
        target="orders",
        parameters={"tenant_id": "T1", "sku": "SKU1", "qty": 1},
        environment="comos-local",
        decision_ref="decision-observer-v1-001",
    )

    scope = AuthorizationScope(
        principal="agent-123",
        action="retail_sale",
        target="orders",
        environment="comos-local",
        parameter_constraints={"tenant_id": "T1", "sku": "SKU1"},
    )

    # Step 5: Issue authority with DecisionRecord
    authority = issue_authority(intent, scope, decision_record=decision_record)

    return authority, evidence_item, decision_record


def test_1_known_2500_allows_commit():
    """Test 1: KNOWN/2500 → ALLOW → COMMIT.

    Observer v1 envelope: tenant T1, SKU1, price_cents=2500, state=KNOWN
    AEE condition: state_equals=KNOWN, value_equals=2500
    Expected: COMMIT with reason VALID, effect NOT_EXECUTED
    """
    envelope = _golden_observer_envelope()
    authority, evidence, record = _make_price_authority_with_observer_v1(
        envelope, aee_value_equals=2500
    )

    # Production flow: prepare → final_authority_check → commit
    prepared = prepare(authority, context_epoch=1)

    # Re-supply same evidence at commit time (simulating current state)
    check_result = final_authority_check(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert check_result == "VALID"

    commit_result = commit(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert commit_result == {
        "decision": "COMMIT",
        "reason": "VALID",
        "applied": True,
        "effect": "NOT_EXECUTED",
    }


def test_2_known_2500_condition_requires_2600_blocks():
    """Test 2: KNOWN/2500 → condition requires 2600 → BLOCK.

    Observer v1 envelope: tenant T1, SKU1, price_cents=2500, state=KNOWN
    AEE condition: state_equals=KNOWN, value_equals=2600
    Expected: BLOCK with reason AEE_CONDITION_FAILED:VALUE_MISMATCH
    """
    envelope = _golden_observer_envelope()
    authority, evidence, record = _make_price_authority_with_observer_v1(
        envelope, aee_value_equals=2600
    )

    prepared = prepare(authority, context_epoch=1)

    check_result = final_authority_check(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert check_result == "AEE_CONDITION_FAILED:VALUE_MISMATCH"

    commit_result = commit(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert commit_result == {
        "decision": "BLOCK",
        "reason": "AEE_CONDITION_FAILED:VALUE_MISMATCH",
        "applied": False,
        "effect": "NONE",
    }


def test_3_unknown_blocks():
    """Test 3: UNKNOWN → BLOCK.

    Observer v1 envelope: state=UNKNOWN, value=null
    AEE condition: state_equals=KNOWN
    Expected: BLOCK with reason AEE_CONDITION_FAILED:STATE_MISMATCH
    """
    envelope = _golden_observer_envelope()
    envelope["observed_state"] = "UNKNOWN"
    envelope["observed_value"] = None

    # Re-compute evidence_id and integrity for modified envelope
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

    authority, evidence, record = _make_price_authority_with_observer_v1(
        envelope, aee_value_equals=2500
    )

    prepared = prepare(authority, context_epoch=1)

    check_result = final_authority_check(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert check_result == "AEE_CONDITION_FAILED:STATE_MISMATCH"

    commit_result = commit(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert commit_result == {
        "decision": "BLOCK",
        "reason": "AEE_CONDITION_FAILED:STATE_MISMATCH",
        "applied": False,
        "effect": "NONE",
    }


def test_4_stale_blocks():
    """Test 4: STALE → BLOCK.

    Observer v1 envelope: old observed_at (STALE freshness)
    AEE condition: freshness_equals=FRESH
    Expected: BLOCK with reason AEE_CONDITION_FAILED:FRESHNESS_MISMATCH
    """
    envelope = _golden_observer_envelope()
    # Set observed_at to 2 hours ago (beyond 3600s threshold)
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope["observed_at"] = old_time

    # Re-compute evidence_id and integrity for modified envelope
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

    authority, evidence, record = _make_price_authority_with_observer_v1(
        envelope, aee_value_equals=2500
    )

    # Add freshness_equals=FRESH to AEE condition
    aee_condition = AEECondition(
        condition_id="condition-price-observer-v1",
        evidence_ref=envelope["evidence_id"],
        state_equals="KNOWN",
        value_equals=2500,
        freshness_equals="FRESH",
    )

    # Re-create DecisionRecord with freshness condition
    record = DecisionRecord(
        decision_id="decision-observer-v1-001",
        decision_time="2026-10-03T19:00:01Z",
        intent_ref="intent-observer-v1-001",
        authorization_scope_ref="scope-observer-v1-001",
        evidence_items=(evidence,),
        aee_conditions=(aee_condition,),
    )

    intent = RuntimeIntent(
        principal="agent-123",
        action="retail_sale",
        target="orders",
        parameters={"tenant_id": "T1", "sku": "SKU1", "qty": 1},
        environment="comos-local",
        decision_ref="decision-observer-v1-001",
    )

    scope = AuthorizationScope(
        principal="agent-123",
        action="retail_sale",
        target="orders",
        environment="comos-local",
        parameter_constraints={"tenant_id": "T1", "sku": "SKU1"},
    )

    authority = issue_authority(intent, scope, decision_record=record)

    prepared = prepare(authority, context_epoch=1)

    check_result = final_authority_check(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert check_result == "AEE_CONDITION_FAILED:FRESHNESS_MISMATCH"

    commit_result = commit(
        prepared,
        current_epoch=1,
        current_evidence={evidence.evidence_ref: evidence},
    )
    assert commit_result == {
        "decision": "BLOCK",
        "reason": "AEE_CONDITION_FAILED:FRESHNESS_MISMATCH",
        "applied": False,
        "effect": "NONE",
    }


def test_5_tampered_evidence_rejected_before_aee():
    """Test 5: tampered evidence → REJECT BEFORE AEE.

    Observer v1 envelope: observed_value tampered without integrity recalculation
    Expected: adapter rejects with ValueError about integrity mismatch
    """
    envelope = _golden_observer_envelope()
    envelope["observed_value"] = 9999  # Tampered value
    # Original integrity digest unchanged (will not match)

    try:
        observer_v1_envelope_to_evidence(envelope, evaluation_status="USED")
        assert False, "Should reject tampered envelope"
    except ValueError as exc:
        assert "integrity digest does not match" in str(exc)
        # Distinct from VALUE_MISMATCH - this is security rejection before AEE


def test_6_evidence_id_mismatch_rejected_before_aee():
    """Test 6: evidence_id mismatch → REJECT BEFORE AEE.

    Observer v1 envelope: subject changed (T1→T2), integrity recalc'd, but original evidence_id unchanged
    Expected: adapter rejects with ValueError about evidence_id mismatch
    """
    envelope = _golden_observer_envelope()
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
        # Distinct from predicate failure - this is identity rejection before AEE


def test_7_conflicting_observations_remain_independent():
    """Test 7: conflicting observations remain independent.

    Two valid Observer v1 evidence with same subject/target but different values (2500 vs 2600).
    Both must:
    - Successfully pass adapter
    - Have different evidence_ref
    - Remain independent EvidenceItem
    Observer/adapter does not decide which is "true".
    """
    envelope_a = _golden_observer_envelope()
    envelope_a["observed_value"] = 2500

    # Re-compute evidence_id and integrity for envelope_a
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

    # Re-compute evidence_id and integrity for envelope_b
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

    # Convert both envelopes
    evidence_a = observer_v1_envelope_to_evidence(
        envelope_a, evaluation_status="USED", role="commit_condition"
    )
    evidence_b = observer_v1_envelope_to_evidence(
        envelope_b, evaluation_status="USED", role="commit_condition"
    )

    # Verify they are independent
    assert evidence_a.evidence_ref != evidence_b.evidence_ref
    assert evidence_a.value == 2500
    assert evidence_b.value == 2600
    assert evidence_a.evidence_ref == envelope_a["evidence_id"]
    assert evidence_b.evidence_ref == envelope_b["evidence_id"]

    # Both can coexist in evidence dict
    evidence_dict = {
        evidence_a.evidence_ref: evidence_a,
        evidence_b.evidence_ref: evidence_b,
    }
    assert len(evidence_dict) == 2
