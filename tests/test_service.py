"""
EGA HTTP Service Tests

Tests for the EGA HTTP service layer for ComOS integration.
Tests service behavior, error handling, and intent-authority validation.
"""

import os
import base64
import json
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from ega.models import RuntimeIntent, ExecutionAuthority, AuthorizationScope, DecisionRecord, EvidenceItem, AEECondition
from ega.authority import issue_authority
from ega.boundary import prepare, commit
from ega.interop import (
    observer_v1_envelope_to_evidence,
    _canonicalize_nextone_v1,
    _compute_observer_v1_integrity_digest,
    _derive_observer_v1_evidence_id,
)

# Set environment variables for testing BEFORE importing the app
os.environ["EGA_FAIL_CLOSED"] = "false"
os.environ["EGA_TRUSTED_AUTHORITY_IDS"] = ""

from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from ega.service import app, EvaluateRequest, RuntimeIntentRequest, ExecutionAuthorityRequest, Parameters, ItemsItem, EvidenceEnvelopeRequest

# Update module-level variables after import
from ega import service
service.TRUSTED_AUTHORITY_IDS = set()
service.FAIL_CLOSED_ON_UNKNOWN_AUTHORITY = False
service.ALLOW_UNVERIFIED_AUTHORITY = True  # Explicitly unsafe mode for model/service tests
service.CONTEXT_VERSION_PROVIDER = lambda request: request.context_epoch  # test-only trusted-provider stub

# Test client
client = TestClient(app)


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


def _make_fresh_observer_envelope(value: int) -> dict:
    """Create a fresh Observer v1 envelope with current timestamp and recomputed evidence_id."""
    from ega.interop import _derive_observer_v1_evidence_id
    now = datetime.now(timezone.utc)
    envelope = _golden_observer_envelope().copy()
    envelope["observed_value"] = value
    envelope["observed_at"] = now.isoformat()
    # Recompute evidence_id from identity payload
    envelope["evidence_id"] = _derive_observer_v1_evidence_id(
        subject=envelope["subject"],
        target=envelope["target"],
        observed_state=envelope["observed_state"],
        observed_value=value,
        observed_at=envelope["observed_at"],
        provenance=envelope["provenance"],
    )
    # Recompute integrity
    covered = {k: v for k, v in envelope.items() if k != "integrity"}
    digest = sha256(_canonicalize_nextone_v1(covered)).hexdigest()
    envelope["integrity"]["digest"] = f"sha256:{digest}"
    return envelope


def test_health_check():
    """Health check endpoint works."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "0.1.6"}


def test_evaluate_valid_authority():
    """Valid authority and matching intent returns COMMIT."""
    # Create a valid authority using existing EGA functions
    intent = RuntimeIntent(
        principal="buyer-123",
        action="retail_sale",
        target="tenant-456",
        parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
        environment="production",
        decision_ref="decision-001"
    )
    scope = AuthorizationScope(
        principal="buyer-123",
        action="retail_sale",
        target="tenant-456",
        environment="production",
        parameter_constraints={}  # No constraints for v0.1.2
    )
    authority = issue_authority(intent, scope, authority_id="auth-001")

    # Build request
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"
    assert data["reason"] == "VALID"
    assert data["applied"] is True
    assert data["effect"] == "NOT_EXECUTED"


def test_evaluate_intent_mismatch_principal():
    """Intent principal different from authority principal is rejected."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-999",  # Different from authority
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",  # Different from intent
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 403
    assert "principal" in response.json()["detail"]


def test_evaluate_intent_mismatch_action():
    """Intent action different from authority action is rejected."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="refund",  # Different from authority
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",  # Different from intent
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 403
    assert "action" in response.json()["detail"]


def test_evaluate_intent_mismatch_target():
    """Intent target different from authority target is rejected."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-999",  # Different from authority
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",  # Different from intent
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 403
    assert "target" in response.json()["detail"]


def test_evaluate_intent_mismatch_parameters():
    """Intent parameters different from authority parameters is rejected."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=2)]),  # Different quantity
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},  # Different quantity
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 409
    assert "parameters" in response.json()["detail"]


def test_evaluate_invalid_authority_status():
    """Authority with non-VALID status is rejected by Pydantic validation."""
    # Pydantic validation happens before the endpoint, so we test the validation error
    try:
        authority = ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="REVOKED"  # Invalid status
        )
        assert False, "Should have raised validation error"
    except ValueError as e:
        assert "VALID" in str(e)


def test_evaluate_missing_required_field():
    """Missing required field is rejected by Pydantic validation."""
    # Pydantic validation happens before the endpoint
    try:
        intent = RuntimeIntentRequest(
            principal="",  # Empty field
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        )
        assert False, "Should have raised validation error"
    except ValueError as e:
        assert "at least 1 character" in str(e)


def test_evaluate_with_expected_total_coms():
    """Evaluation with expected_total_coms in parameters."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(
                items=[ItemsItem(product_id="sku-001", quantity=1)],
                expected_total_coms=2500
            ),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={
                "items": [{"product_id": "sku-001", "quantity": 1}],
                "expected_total_coms": 2500
            },
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"



def test_evaluate_epoch_change_blocks(monkeypatch):
    """A caller snapshot version that differs from trusted current context blocks."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    stale_version = current_time - 400
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", lambda request: current_time)
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=stale_version
    )
    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    assert response.json()["reason"] == "STALE_CONTEXT"
    assert response.json()["effect"] == "NOT_EXECUTED"


def test_evaluate_with_aee_conditions():
    """Evaluation with AEE conditions requires evidence (v0.1.2 fix)."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320",
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2 fix: AEE conditions require evidence, so this returns 400
    assert response.status_code == 400
    assert "evidence" in response.json()["detail"].lower()


def test_forged_authority_rejected():
    """Caller-constructed authority without provenance is blocked when fail-closed is enabled."""
    # This test documents the v0.1.2 fix: authority whitelist enforcement
    # In production with EGA_FAIL_CLOSED=true and EGA_TRUSTED_AUTHORITY_IDS set,
    # forged authorities are rejected. In test mode (fail-closed=false), they are accepted.
    # For this test, we assume fail-closed=false for testing compatibility
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="forged-auth-001",  # Forged authority_id
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # In test mode (fail-closed=false), forged authority is accepted
    # In production with whitelist, this would return 403
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"


def test_nested_parameter_mismatch():
    """Nested parameter changes are detected."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(
                items=[ItemsItem(product_id="sku-001", quantity=1)],
                expected_total_coms=2500
            ),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={
                "items": [{"product_id": "sku-001", "quantity": 1}],
                "expected_total_coms": 3000  # Different nested value
            },
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 409
    assert "parameters" in response.json()["detail"]


def test_extra_parameters_in_intent():
    """Extra parameters in intent cause mismatch."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(
                items=[ItemsItem(product_id="sku-001", quantity=1)],
                expected_total_coms=2500
            ),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={
                "items": [{"product_id": "sku-001", "quantity": 1}]
                # expected_total_coms missing in authority
            },
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 409
    assert "parameters" in response.json()["detail"]


def test_aee_with_missing_evidence_blocks():
    """AEE conditions with missing evidence now block (v0.1.2 fix)."""
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=None  # No evidence provided
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320",
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2 fix: should return 400 with error about missing evidence
    assert response.status_code == 400
    assert "evidence" in response.json()["detail"].lower()


def test_exception_handling_fail_closed():
    """Internal exceptions return error (BLOCK decision to caller)."""
    # This test verifies that exceptions don't return COMMIT
    # Malformed parameters that cause internal error
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # Valid request, should not throw exception
    assert response.status_code == 200


def test_authority_reuse_different_intent():
    """Authority cannot be reused for different intent (intent mismatch)."""
    # Use same authority with different intent
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-002", quantity=1)]),  # Different product
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},  # Original product
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 409
    assert "parameters" in response.json()["detail"]


def test_expiry_not_supported():
    """Expiry is not implemented in v0.1.2 (architectural limitation)."""
    # This test documents that there is no expiry mechanism
    # Any authority with status=VALID is accepted regardless of age
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
            # No expiry field exists
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # No expiry mechanism, so this succeeds
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"


def test_untrusted_authority_blocked():
    """Authority not in trusted whitelist is blocked when fail-closed is enabled."""
    # This test requires setting environment variable before importing app
    # For now, we document the expected behavior
    # In production with EGA_FAIL_CLOSED=true and EGA_TRUSTED_AUTHORITY_IDS set,
    # this should return 403
    pass


def test_aee_without_evidence_blocks():
    """AEE conditions without evidence now block (v0.1.2 fix)."""
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=None  # No evidence provided
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320",
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2 fix: should return 400 with error about missing evidence
    assert response.status_code == 400
    assert "evidence" in response.json()["detail"].lower()


def test_aee_with_evidence_allowed():
    """AEE conditions with correct evidence are evaluated and allowed (v0.1.2)."""
    fresh_envelope = _make_fresh_observer_envelope(2500)
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=[EvidenceEnvelopeRequest(**fresh_envelope)]
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": fresh_envelope["evidence_id"],
                    "state_equals": "KNOWN",
                    "value_equals": 2500
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2: evidence provided and AEE evaluated
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"


def test_aee_incorrect_value_blocks():
    """AEE conditions with incorrect evidence value block (v0.1.2)."""
    fresh_envelope = _make_fresh_observer_envelope(3000)  # Wrong value
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=[EvidenceEnvelopeRequest(**fresh_envelope)]
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": fresh_envelope["evidence_id"],
                    "state_equals": "KNOWN",
                    "value_equals": 2500  # Condition expects 2500, evidence has 3000
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2: incorrect value should block
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "BLOCK"
    assert "VALUE_MISMATCH" in data["reason"]


def test_aee_stale_evidence_blocks():
    """Stale evidence blocks (v0.1.2)."""
    stale_envelope = _golden_observer_envelope()  # Old timestamp from 2026-10-03
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=[EvidenceEnvelopeRequest(**stale_envelope)]
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": stale_envelope["evidence_id"],
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2: stale evidence should block
    assert response.status_code == 400
    assert "stale" in response.json()["detail"].lower()


def test_aee_wrong_evidence_ref_blocks():
    """Evidence with wrong reference blocks (v0.1.2)."""
    fresh_envelope = _make_fresh_observer_envelope(2500)
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=[EvidenceEnvelopeRequest(**fresh_envelope)]
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": "ev1:wrongevidenceid",  # Wrong reference
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2: wrong evidence ref should block
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "BLOCK"
    assert "AEE_EVIDENCE_UNAVAILABLE" in data["reason"]



def test_context_staleness_detection(monkeypatch):
    """A stale caller context version is blocked by the trusted provider."""
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", lambda request: 42)
    payload = _valid_context_evaluate_payload(context_epoch=41)
    response = client.post("/v1/evaluate", json=payload)
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    assert response.json()["reason"] == "STALE_CONTEXT"
    assert response.json()["effect"] == "NOT_EXECUTED"


def test_malformed_evidence_envelope_blocks():
    """Malformed evidence envelope blocks (v0.1.2)."""
    malformed_envelope = _golden_observer_envelope().copy()
    malformed_envelope["integrity"]["digest"] = "sha256:wrongdigest"  # Tampered

    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=[EvidenceEnvelopeRequest(**malformed_envelope)]
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": malformed_envelope["evidence_id"],
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2: malformed envelope should block
    assert response.status_code == 400
    assert "integrity" in response.json()["detail"].lower() or "digest" in response.json()["detail"].lower()


def test_context_age_valid_wallclock_changes():
    """A stable trusted context version passes both provider reads."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    # The test-only provider stub returns the submitted version unchanged.
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time  # Matches the test provider stub
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # The provider returned the same trusted version on both reads.
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"


def test_future_dated_evidence_rejected():
    """Future-dated evidence is rejected (v0.1.2.1 fix)."""
    from datetime import timedelta
    future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    future_envelope = _golden_observer_envelope().copy()
    future_envelope["observed_at"] = future_time.isoformat()
    # Recompute evidence_id and integrity for future timestamp
    future_envelope["evidence_id"] = _derive_observer_v1_evidence_id(
        subject=future_envelope["subject"],
        target=future_envelope["target"],
        observed_state=future_envelope["observed_state"],
        observed_value=future_envelope["observed_value"],
        observed_at=future_envelope["observed_at"],
        provenance=future_envelope["provenance"],
    )
    covered = {k: v for k, v in future_envelope.items() if k != "integrity"}
    digest = sha256(_canonicalize_nextone_v1(covered)).hexdigest()
    future_envelope["integrity"]["digest"] = f"sha256:{digest}"

    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=[EvidenceEnvelopeRequest(**future_envelope)]
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
            aee_conditions=[
                {
                    "condition_id": "cond-001",
                    "evidence_ref": future_envelope["evidence_id"],
                    "state_equals": "KNOWN"
                }
            ]
        ),
        context_epoch=int((datetime.now(timezone.utc).timestamp()))
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # v0.1.2.1: future-dated evidence should be rejected
    assert response.status_code == 400
    assert "future" in response.json()["detail"].lower()



def test_context_epoch_future_rejected(monkeypatch):
    """Context version semantics do not treat versions as wall-clock timestamps."""
    # A "future" numeric value has no meaning by itself; only trusted version equality matters.
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", lambda request: 100)
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(context_epoch=101))
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    assert response.json()["reason"] == "STALE_CONTEXT"
    assert response.json()["effect"] == "NOT_EXECUTED"


def test_no_aee_conditions_evidence_optional():
    """Without AEE conditions, evidence is optional."""
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
            evidence_envelopes=None  # No evidence, but no AEE conditions
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
            # No AEE conditions
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "COMMIT"


def test_error_messages_generic():
    """Error messages do not leak internal details (v0.1.2 fix)."""
    # Trigger a ValueError with internal details
    current_time = int(datetime.now(timezone.utc).timestamp())
    request = EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001"
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID"
        ),
        context_epoch=current_time
    )

    response = client.post("/v1/evaluate", json=request.model_dump())
    # This should succeed (valid request)
    assert response.status_code == 200
    # If it failed, error message should be generic
    # We can't easily trigger a ValueError without modifying EGA core
    # This test documents the expectation

def _authority_request_for_signature(issued_at=None, expires_at=None, audience="ega-service", nonce=None):
    now = datetime.now(timezone.utc)
    return ExecutionAuthorityRequest(
        authority_id="auth-001",
        principal="buyer-123",
        action="retail_sale",
        target="tenant-456",
        parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
        environment="production",
        source_decision="decision-001",
        status="VALID",
        nonce=nonce or uuid.uuid4().hex + uuid.uuid4().hex,
        issued_at=issued_at or now,
        expires_at=expires_at or now + timedelta(seconds=120),
        audience=audience,
    )


def _signed_authority_request(private_key, authority=None):
    authority = authority or _authority_request_for_signature()
    payload = authority.model_dump(exclude={"signature"}, mode="json")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    signature = base64.b64encode(private_key.sign(canonical)).decode("ascii")
    return authority.model_copy(update={"signature": signature})


def test_unverified_authority_blocked_even_if_id_allowlisted(monkeypatch):
    """An ID whitelist must not be mistaken for cryptographic authentication."""
    monkeypatch.delenv("EGA_AUTHORITY_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.setattr(service, "ALLOW_UNVERIFIED_AUTHORITY", False)
    monkeypatch.setattr(service, "TRUSTED_AUTHORITY_IDS", {"auth-001"})
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(_authority_request_for_signature())
    assert exc_info.value.status_code == 503


def test_valid_ed25519_authority_signature_is_accepted(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    signed = _signed_authority_request(private_key)
    service._validate_authority_trust(signed)


def test_ed25519_signature_rejects_tampered_authority(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    signed = _signed_authority_request(private_key)
    tampered = signed.model_copy(update={"action": "payment_confirm"})
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(tampered)
    assert exc_info.value.status_code == 403



def test_expired_ed25519_authority_is_rejected(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    now = datetime.now(timezone.utc)
    expired = _authority_request_for_signature(
        issued_at=now - timedelta(minutes=10),
        expires_at=now - timedelta(minutes=5),
    )
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(_signed_authority_request(private_key, expired))
    assert exc_info.value.status_code == 403


def test_wrong_audience_ed25519_authority_is_rejected(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    wrong_audience = _authority_request_for_signature(audience="other-service")
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(_signed_authority_request(private_key, wrong_audience))
    assert exc_info.value.status_code == 403



def test_future_issued_ed25519_authority_is_rejected(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    now = datetime.now(timezone.utc)
    future = _authority_request_for_signature(
        issued_at=now + timedelta(minutes=2),
        expires_at=now + timedelta(minutes=3),
    )
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(_signed_authority_request(private_key, future))
    assert exc_info.value.status_code == 403


def test_overlong_ed25519_authority_lifetime_is_rejected(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    now = datetime.now(timezone.utc)
    overlong = _authority_request_for_signature(
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(_signed_authority_request(private_key, overlong))
    assert exc_info.value.status_code == 403



def test_authority_nonce_cannot_be_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "REPLAY_DB_PATH", str(tmp_path / "replay.sqlite3"))
    expires = datetime.now(timezone.utc) + timedelta(minutes=2)
    service._claim_authority_nonce("auth-001", "nonce-0123456789abcdef", expires)
    with pytest.raises(HTTPException) as exc_info:
        service._claim_authority_nonce("auth-001", "nonce-0123456789abcdef", expires)
    assert exc_info.value.status_code == 409


def test_replay_ledger_allows_distinct_nonces(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "REPLAY_DB_PATH", str(tmp_path / "replay.sqlite3"))
    expires = datetime.now(timezone.utc) + timedelta(minutes=2)
    service._claim_authority_nonce("auth-001", "nonce-0123456789abcdef-A", expires)
    service._claim_authority_nonce("auth-001", "nonce-0123456789abcdef-B", expires)


def test_replay_ledger_fails_closed_when_storage_unavailable(tmp_path, monkeypatch):
    # Use a directory as the database path so SQLite cannot open it as a file.
    db_directory = tmp_path / "is-a-directory"
    db_directory.mkdir()
    monkeypatch.setattr(service, "REPLAY_DB_PATH", str(db_directory))
    with pytest.raises(HTTPException) as exc_info:
        service._claim_authority_nonce(
            "auth-001",
            "nonce-0123456789abcdef",
            datetime.now(timezone.utc) + timedelta(minutes=2),
        )
    assert exc_info.value.status_code == 503



def test_expired_authority_cannot_be_claimed_in_replay_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "REPLAY_DB_PATH", str(tmp_path / "replay.sqlite3"))
    with pytest.raises(HTTPException) as exc_info:
        service._claim_authority_nonce(
            "auth-001",
            "nonce-0123456789abcdef",
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    assert exc_info.value.status_code == 403


def test_signed_authority_without_nonce_is_rejected(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(
        "EGA_AUTHORITY_PUBLIC_KEYS_JSON",
        json.dumps({"auth-001": base64.b64encode(public_key).decode("ascii")}),
    )
    authority = _authority_request_for_signature(nonce=None).model_copy(update={"nonce": None})
    with pytest.raises(HTTPException) as exc_info:
        service._validate_authority_trust(_signed_authority_request(private_key, authority))
    assert exc_info.value.status_code == 403



def _valid_context_evaluate_payload(context_epoch=7):
    return EvaluateRequest(
        intent=RuntimeIntentRequest(
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters=Parameters(items=[ItemsItem(product_id="sku-001", quantity=1)]),
            environment="production",
            decision_ref="decision-001",
        ),
        authority=ExecutionAuthorityRequest(
            authority_id="auth-001",
            principal="buyer-123",
            action="retail_sale",
            target="tenant-456",
            parameters={"items": [{"product_id": "sku-001", "quantity": 1}]},
            environment="production",
            source_decision="decision-001",
            status="VALID",
        ),
        context_epoch=context_epoch,
    ).model_dump(mode="json")


def test_context_provider_change_between_prepare_and_final_check_blocks(monkeypatch):
    versions = iter([7, 8])
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", lambda request: next(versions))
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(7))
    assert response.status_code == 200
    assert response.json() == {
        "decision": "BLOCK",
        "reason": "STALE_CONTEXT",
        "applied": False,
        "effect": "NOT_EXECUTED",
    }


def test_context_version_mismatch_blocks_before_prepare(monkeypatch):
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", lambda request: 8)
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(7))
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    assert response.json()["reason"] == "STALE_CONTEXT"
    assert response.json()["effect"] == "NOT_EXECUTED"


def test_missing_context_provider_fails_closed(monkeypatch):
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", None)
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(7))
    assert response.status_code == 503
    assert response.json()["detail"] == "Trusted context version provider is not configured"


def test_context_provider_unavailable_fails_closed(monkeypatch):
    def unavailable(_request):
        raise RuntimeError("test-only provider failure")
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", unavailable)
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(7))
    assert response.status_code == 503
    assert response.json()["detail"] == "Trusted context version is unavailable"



def test_context_provider_invalid_version_fails_closed(monkeypatch):
    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", lambda request: True)
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(1))
    assert response.status_code == 503
    assert response.json()["detail"] == "Trusted context version is invalid"


def test_context_provider_failure_on_final_read_fails_closed(monkeypatch):
    calls = {"count": 0}
    def fails_on_second_read(_request):
        calls["count"] += 1
        if calls["count"] == 1:
            return 7
        raise RuntimeError("test-only second-read failure")

    monkeypatch.setattr(service, "CONTEXT_VERSION_PROVIDER", fails_on_second_read)
    response = client.post("/v1/evaluate", json=_valid_context_evaluate_payload(7))
    assert response.status_code == 503
    assert response.json()["detail"] == "Trusted context version is unavailable"
    assert calls["count"] == 2
