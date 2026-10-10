from pathlib import Path
"""
Independent EGA → ComOS Integration Test Harness

This harness tests the EGA → ComOS integration contract independently
without connecting to a real ComOS instance or modifying ComOS source.

Purpose:
- Validate EGA service contract for ComOS order_create
- Test authorization logic, scope checking, and freshness
- Simulate ComOS adapter behavior
- No real ComOS effects are enforced or claimed

ComOS Integration Adapter Contract:
The actual ComOS integration is an explicit contract for Ron to implement locally.
This harness tests the EGA side of that contract only.
"""

import pytest
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ega.aee import evaluate_aee_condition
from ega.authority import issue_authority
from ega.boundary import commit, prepare
from ega.models import (
    ExecutionAuthority,
    DecisionRecord,
    RuntimeIntent,
    AuthorizationScope,
    AEECondition,
    EvidenceItem
)


class ComOSAdapterError(Enum):
    """ComOS adapter error types."""
    INVALID_AUTHORITY = "invalid_ega_authority"
    SCOPE_VIOLATION = "ega_scope_violation"
    DECISION_STALE = "ega_decision_stale"
    AUTHORITY_REQUIRED = "ega_authority_required"
    SERVICE_UNAVAILABLE = "ega_service_unavailable"
    MALFORMED_RESPONSE = "ega_malformed_response"


@dataclass
class ComOSOrderCreateIntent:
    """Canonical intent for EGA → ComOS order_create binding."""
    principal: str  # ComOS buyer_root (manager root from OAuth token)
    action: str     # "order_create" (hub tool name)
    target: str     # vendor tenant_id (business entity)
    environment: str  # "production" or from config
    parameters: Dict[str, Any] = field(default_factory=dict)
    source_decision: str = ""  # EGA decision record reference
    governance_context: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, EvidenceItem] = field(default_factory=dict)


@dataclass
class SimulatedComOSEffect:
    """Simulated ComOS protected effect (for testing only)."""
    effect_type: str  # "per_act_charge", "enqueue", "record_insert", etc.
    occurred: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class SimulatedComOSAdapter:
    """
    Simulated ComOS adapter for EGA integration testing.

    This simulates the ComOS-side logic that would call the EGA service
    at the enforcement seam. It does NOT connect to a real ComOS instance.
    """

    def __init__(self, ega_service_url: str = "http://localhost:8000"):
        self.ega_service_url = ega_service_url
        self.simulated_effects: list[SimulatedComOSEffect] = []
        self.ega_available: bool = True
        self.ega_malformed: bool = False

    def reset_effects(self):
        """Reset simulated effects between tests."""
        self.simulated_effects = []

    def _simulate_per_act_charge(self) -> SimulatedComOSEffect:
        """Simulate per-act charge (first protected effect)."""
        effect = SimulatedComOSEffect(
            effect_type="per_act_charge",
            occurred=True,
            details={"charged": True, "amount": 1}
        )
        self.simulated_effects.append(effect)
        return effect

    def _simulate_enqueue(self) -> SimulatedComOSEffect:
        """Simulate ACT enqueue (second protected effect)."""
        effect = SimulatedComOSEffect(
            effect_type="enqueue",
            occurred=True,
            details={"enqueued": True}
        )
        self.simulated_effects.append(effect)
        return effect

    def _simulate_record_insert(self) -> SimulatedComOSEffect:
        """Simulate hub-side record insertion (third protected effect)."""
        effect = SimulatedComOSEffect(
            effect_type="record_insert",
            occurred=True,
            details={"inserted": True}
        )
        self.simulated_effects.append(effect)
        return effect

    def _compensate_charge(self):
        """Simulate charge compensation on failure."""
        effect = SimulatedComOSEffect(
            effect_type="charge_compensated",
            occurred=True,
            details={"compensated": True}
        )
        self.simulated_effects.append(effect)

    def check_ega_authority(
        self,
        authority: Optional[ExecutionAuthority],
        runtime_intent: ComOSOrderCreateIntent,
        current_epoch: int,
        current_evidence: Dict[str, EvidenceItem]
    ) -> tuple[bool, Optional[ComOSAdapterError], str]:
        """
        Simulate ComOS calling EGA service at enforcement seam.

        Returns:
            (allowed, error, reason)
        """
        if not self.ega_available:
            return (False, ComOSAdapterError.SERVICE_UNAVAILABLE, "EGA service unavailable")

        if self.ega_malformed:
            return (False, ComOSAdapterError.MALFORMED_RESPONSE, "EGA service returned malformed response")

        if authority is None:
            return (False, ComOSAdapterError.AUTHORITY_REQUIRED, "EGA authority is required")

        # Simulate scope check
        if (authority.principal != runtime_intent.principal or
            authority.action != runtime_intent.action or
            authority.target != runtime_intent.target):
            return (False, ComOSAdapterError.SCOPE_VIOLATION, "Runtime intent outside EGA authorization scope")

        # Simulate parameter check
        authority_params = authority.parameters
        runtime_params = runtime_intent.parameters
        if authority_params.get("items") != runtime_params.get("items"):
            return (False, ComOSAdapterError.SCOPE_VIOLATION, "Parameters do not match authority")

        # Simulate freshness check (simplified)
        # In real implementation, this would check decision timestamp
        # For this harness, we use the EGA commit() logic

        # Use EGA's actual commit logic
        prepared = prepare(authority, context_epoch=current_epoch)
        commit_result = commit(
            prepared,
            current_epoch=current_epoch,
            current_evidence=current_evidence
        )

        if commit_result["decision"] == "BLOCK":
            if "stale" in commit_result["reason"].lower():
                return (False, ComOSAdapterError.DECISION_STALE, commit_result["reason"])
            return (False, ComOSAdapterError.SCOPE_VIOLATION, commit_result["reason"])

        return (True, None, "EGA authorization passed")

    def attempt_order_create(
        self,
        authority: Optional[ExecutionAuthority],
        runtime_intent: ComOSOrderCreateIntent,
        current_epoch: int,
        current_evidence: Dict[str, EvidenceItem]
    ) -> tuple[bool, Optional[ComOSAdapterError], str, list[SimulatedComOSEffect]]:
        """
        Simulate the complete order_create flow with EGA enforcement.

        This simulates the order of operations as documented in
        comos-seam-location-correction.md:
        1. EGA check (before beginPerActCharge)
        2. Per-act charge (if EGA passes)
        3. ACT enqueue (if charge succeeds)
        4. Record insert (if enqueue succeeds)

        Returns:
            (success, error, reason, effects)
        """
        self.reset_effects()

        # Phase 1: EGA check (before any protected effects)
        allowed, error, reason = self.check_ega_authority(
            authority, runtime_intent, current_epoch, current_evidence
        )

        if not allowed:
            # EGA BLOCK - no protected effects occur
            return (False, error, reason, self.simulated_effects)

        # Phase 2: Per-act charge (first protected effect)
        charge_effect = self._simulate_per_act_charge()

        # Phase 3: ACT enqueue (second protected effect)
        enqueue_effect = self._simulate_enqueue()

        # Phase 4: Record insert (third protected effect)
        record_effect = self._simulate_record_insert()

        return (True, None, "Order created successfully", self.simulated_effects)


def create_test_evidence(price: int, product_id: str = "prod-001") -> EvidenceItem:
    """Create test evidence for AEE conditions."""
    return EvidenceItem(
        evidence_ref="evidence-baseline",
        digest=f"sha256-{hash(str(price))}",
        observed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        evaluation_status="USED",
        role="commit_condition",
        target=product_id,
        state="KNOWN",
        value={
            "tenant_id": "federation-retail",
            "product_id": product_id,
            "price": price,
            "active": True
        },
        freshness="FRESH",
        uncertainty=0.0,
        provenance="observer"
    )


def create_test_authority(
    principal: str = "manager-root-abc123",
    target: str = "federation-retail",
    items: list = None,
    decision_ref: str = "decision-ega-001"
) -> ExecutionAuthority:
    """Create a test EGA authority."""
    if items is None:
        items = [{"product_id": "prod-001", "quantity": 1}]

    evidence = create_test_evidence(price=2500)

    aee_condition = AEECondition(
        condition_id="condition-price-2500",
        evidence_ref="evidence-baseline",
        value_equals={
            "tenant_id": "federation-retail",
            "product_id": "prod-001",
            "price": 2500,
            "active": True
        }
    )

    decision_record = DecisionRecord(
        decision_id=decision_ref,
        decision_time=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        intent_ref="intent-order-create",
        authorization_scope_ref="scope-retail-order",
        evidence_items=(evidence,),
        aee_conditions=(aee_condition,)
    )

    intent = RuntimeIntent(
        principal=principal,
        action="order_create",
        target=target,
        parameters={"items": items},
        environment="production",
        decision_ref=decision_ref
    )

    scope = AuthorizationScope(
        principal=principal,
        action="order_create",
        target=target,
        environment="production"
    )

    return issue_authority(intent, scope, decision_record=decision_record)


# ============================================================================
# TEST CASES
# ============================================================================

def test_valid_authority_exact_matching_intent():
    """
    Test T1: Valid authority and exact matching intent.

    Expected: SUCCESS - all protected effects occur.
    """
    adapter = SimulatedComOSAdapter()

    authority = create_test_authority()
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is True
    assert error is None
    assert reason == "Order created successfully"
    assert len(effects) == 3
    assert effects[0].effect_type == "per_act_charge"
    assert effects[1].effect_type == "enqueue"
    assert effects[2].effect_type == "record_insert"
    assert all(e.occurred for e in effects)


def test_ega_block_with_changed_evidence():
    """
    Test T2: EGA BLOCK when evidence no longer satisfies condition.

    Expected: FAILURE at EGA check - no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()

    authority = create_test_authority()
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    # Evidence changed: price is now 3000, but authority requires 2500
    current_evidence = {"evidence-baseline": create_test_evidence(price=3000)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.SCOPE_VIOLATION
    assert "condition" in reason.lower() or "value" in reason.lower()
    assert len(effects) == 0  # No protected effects occurred
    assert all(not e.occurred for e in effects)


def test_payload_mutation_between_authorization_and_commit():
    """
    Test T3: Payload mutation between authorization and simulated commit.

    Expected: FAILURE at scope check - no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()

    authority = create_test_authority(items=[{"product_id": "prod-001", "quantity": 1}])
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 2}]}  # Mutated!
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.SCOPE_VIOLATION
    assert "parameter" in reason.lower() or "scope" in reason.lower()
    assert len(effects) == 0  # No protected effects occurred


def test_principal_mismatch():
    """
    Test T4a: Principal mismatch.

    Expected: FAILURE at scope check - no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()

    authority = create_test_authority(principal="manager-root-abc123")
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-xyz789",  # Different principal
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.SCOPE_VIOLATION
    assert len(effects) == 0


def test_target_mismatch():
    """
    Test T4b: Target mismatch.

    Expected: FAILURE at scope check - no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()

    authority = create_test_authority(target="federation-retail")
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-wholesale",  # Different target
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.SCOPE_VIOLATION
    assert len(effects) == 0


def test_expired_or_stale_authority():
    """
    Test T5: Expired or stale authority (simulated via stale evidence with freshness requirement).

    Expected: FAILURE at freshness check - no protected effects occur.

    Note: EGA only rejects stale evidence if the AEE condition explicitly requires freshness.
    This test creates an AEE condition that requires FRESH evidence.
    """
    adapter = SimulatedComOSAdapter()

    # Create authority with freshness requirement
    stale_evidence = EvidenceItem(
        evidence_ref="evidence-baseline",
        digest=f"sha256-{hash(2500)}",
        observed_at="2020-01-01T00:00:00Z",  # Very old timestamp
        evaluation_status="USED",
        role="commit_condition",
        target="prod-001",
        state="KNOWN",
        value={
            "tenant_id": "federation-retail",
            "product_id": "prod-001",
            "price": 2500,
            "active": True
        },
        freshness="STALE",  # Stale evidence
        uncertainty=0.0,
        provenance="observer"
    )

    # AEE condition that requires FRESH (not just KNOWN)
    aee_condition = AEECondition(
        condition_id="condition-price-2500-fresh",
        evidence_ref="evidence-baseline",
        value_equals={
            "tenant_id": "federation-retail",
            "product_id": "prod-001",
            "price": 2500,
            "active": True
        },
        state_equals="KNOWN",
        freshness_equals="FRESH"  # Explicitly require FRESH
    )

    decision_record = DecisionRecord(
        decision_id="decision-ega-001",
        decision_time=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        intent_ref="intent-order-create",
        authorization_scope_ref="scope-retail-order",
        evidence_items=(stale_evidence,),
        aee_conditions=(aee_condition,)
    )

    intent = RuntimeIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]},
        environment="production",
        decision_ref="decision-ega-001"
    )

    scope = AuthorizationScope(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production"
    )

    authority = issue_authority(intent, scope, decision_record=decision_record)

    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": stale_evidence}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1,
        current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.SCOPE_VIOLATION
    assert "freshness" in reason.lower() or "stale" in reason.lower()
    assert len(effects) == 0


def test_no_authority_provided():
    """
    Test T6: No authority provided.

    Expected: FAILURE - authority required error, no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()

    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority=None,  # No authority
        runtime_intent=runtime_intent,
        current_epoch=1,
        current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.AUTHORITY_REQUIRED
    assert len(effects) == 0


def test_ega_service_unavailable():
    """
    Test T7: EGA service unavailable.

    Expected: FAILURE - service unavailable error, no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()
    adapter.ega_available = False

    authority = create_test_authority()
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.SERVICE_UNAVAILABLE
    assert len(effects) == 0


def test_ega_malformed_response():
    """
    Test T8: EGA service returns malformed response.

    Expected: FAILURE - malformed response error, no protected effects occur.
    """
    adapter = SimulatedComOSAdapter()
    adapter.ega_malformed = True

    authority = create_test_authority()
    runtime_intent = ComOSOrderCreateIntent(
        principal="manager-root-abc123",
        action="order_create",
        target="federation-retail",
        environment="production",
        parameters={"items": [{"product_id": "prod-001", "quantity": 1}]}
    )

    current_evidence = {"evidence-baseline": create_test_evidence(price=2500)}

    success, error, reason, effects = adapter.attempt_order_create(
        authority, runtime_intent, current_epoch=1, current_evidence=current_evidence
    )

    assert success is False
    assert error == ComOSAdapterError.MALFORMED_RESPONSE
    assert len(effects) == 0


def test_service_replay_ledger_not_covered_by_model_harness():
    """
    The HTTP service has a SQLite replay ledger, but this simulated adapter
    harness uses the core ExecutionAuthority model and does not exercise it.
    Replay behavior is covered separately by the service-level HTTP tests.
    """
    pytest.skip("Service replay protection is tested at the HTTP boundary, not in this simulated harness")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
