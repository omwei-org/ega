from pathlib import Path
"""
EGA Service-Level Integration Tests for ComOS

This test file calls the actual EGA HTTP service endpoint to validate
service-level security guarantees that are not tested by the model-level harness.

Purpose:
- Test service-level validations (HTTP, trust whitelist, wall-clock freshness)
- Test actual HTTP request/response handling
- Complement model-level harness tests
- No real ComOS connection

Architecture:
- Starts EGA service in subprocess
- Makes HTTP requests to POST /v1/evaluate
- Validates service-level behavior
- Shuts down service after tests
"""

import pytest
import time
import subprocess
import signal
import requests
import sys
import hashlib
import json
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ega.models import (
    ExecutionAuthority,
    DecisionRecord,
    RuntimeIntent,
    AuthorizationScope,
    AEECondition,
    EvidenceItem
)


class EGAServiceTestClient:
    """Test client for EGA HTTP service."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url

    def evaluate(
        self,
        authority: Dict[str, Any],
        intent: Dict[str, Any],
        context_epoch: int,
        evidence_envelopes: list = None
    ) -> Dict[str, Any]:
        """Call the EGA service /v1/evaluate endpoint."""
        url = f"{self.base_url}/v1/evaluate"

        payload = {
            "authority": authority,
            "intent": intent,
            "context_epoch": context_epoch
        }

        if evidence_envelopes:
            payload["intent"]["evidence_envelopes"] = evidence_envelopes

        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json()

    def health(self) -> Dict[str, Any]:
        """Call the EGA service /health endpoint."""
        url = f"{self.base_url}/health"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()


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
            "algorithm": "sha256",
            "digest": "2f5a7a3982f8e1c31f8b072f1e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e"
        }
    }


def create_test_authority(
    authority_id: str = "test-auth-001",
    principal: str = "manager-root-abc123",
    target: str = "federation-retail",
    items: list = None
) -> Dict[str, Any]:
    """Create a test authority dict for HTTP request."""
    if items is None:
        items = [{"product_id": "prod-001", "quantity": 1}]

    return {
        "authority_id": authority_id,
        "principal": principal,
        "action": "order_create",
        "target": target,
        "parameters": {"items": items},
        "environment": "production",
        "source_decision": "decision-ega-001",
        "status": "VALID",
        "aee_conditions": [
            {
                "condition_id": "condition-price-2500",
                "evidence_ref": "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320",
                "value_equals": 2500
            }
        ]
    }


def create_test_intent(
    principal: str = "manager-root-abc123",
    target: str = "federation-retail",
    items: list = None
) -> Dict[str, Any]:
    """Create a test intent dict for HTTP request."""
    if items is None:
        items = [{"product_id": "prod-001", "quantity": 1}]

    return {
        "principal": principal,
        "action": "order_create",
        "target": target,
        "parameters": {"items": items},
        "environment": "production",
        "decision_ref": "decision-ega-001"
    }


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def ega_service():
    """Start EGA service for testing."""
    # Start service in subprocess
    env = {
        "EGA_HOST": "127.0.0.1",
        "EGA_PORT": "8000",
        "EGA_TRUSTED_AUTHORITY_IDS": "test-auth-001,test-auth-002",  # Set whitelist
        "EGA_FAIL_CLOSED": "true"  # Fail-closed mode
    }

    proc = subprocess.Popen(
        ["python", "-m", "ega.service"],
        env={**subprocess.os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for service to start
    time.sleep(2)

    yield {
        "process": proc,
        "url": "http://127.0.0.1:8000"
    }

    # Cleanup: shutdown service
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def client(ega_service):
    """Create test client."""
    return EGAServiceTestClient(ega_service["url"])


# ============================================================================
# SERVICE-LEVEL TESTS
# ============================================================================

def test_service_health(client):
    """Test that EGA service is healthy."""
    health = client.health()
    assert health["status"] == "healthy"


def test_service_level_valid_authority(client):
    """
    Service-level test: Valid authority with exact matching intent (no AEE conditions).

    Expected: COMMIT from actual HTTP service.
    """
    authority = create_test_authority(authority_id="test-auth-001")
    # Remove AEE conditions to avoid evidence requirement
    authority["aee_conditions"] = None
    intent = create_test_intent()

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None
        )
    except requests.exceptions.HTTPError as e:
        # Print the error for debugging
        print(f"Error: {e.response.status_code}")
        print(f"Detail: {e.response.json()}")
        raise

    assert result["decision"] == "COMMIT"
    assert result["applied"] is True
    assert result["effect"] in ["NONE", "NOT_EXECUTED"]  # Either is acceptable


def test_service_level_intent_principal_mismatch(client):
    """
    Service-level test: Intent principal mismatch.

    Expected: BLOCK from actual HTTP service (HTTP 403).
    """
    authority = create_test_authority(authority_id="test-auth-001", principal="manager-root-abc123")
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent(principal="manager-root-xyz789")  # Mismatched principal

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 403"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 403
        assert "principal" in e.response.json()["detail"].lower()


def test_service_level_intent_target_mismatch(client):
    """
    Service-level test: Intent target mismatch.

    Expected: BLOCK from actual HTTP service (HTTP 403).
    """
    authority = create_test_authority(authority_id="test-auth-001", target="federation-retail")
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent(target="federation-wholesale")  # Mismatched target

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 403"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 403
        assert "target" in e.response.json()["detail"].lower()


def test_service_level_intent_parameter_mismatch(client):
    """
    Service-level test: Intent parameter mismatch.

    Expected: BLOCK from actual HTTP service (HTTP 409).
    """
    authority = create_test_authority(
        authority_id="test-auth-001",
        items=[{"product_id": "prod-001", "quantity": 1}]
    )
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent(
        items=[{"product_id": "prod-001", "quantity": 2}]  # Mismatched quantity
    )

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 409"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 409
        assert "parameter" in e.response.json()["detail"].lower()


def test_service_level_untrusted_authority(client):
    """
    Service-level test: Authority not in trusted whitelist.

    Expected: BLOCK from actual HTTP service (HTTP 403).
    """
    authority = create_test_authority(authority_id="untrusted-auth-999")  # Not in whitelist
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent()

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 403"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 403
        assert "trusted" in e.response.json()["detail"].lower() or "whitelist" in e.response.json()["detail"].lower()


def test_service_level_stale_context(client):
    """
    Service-level test: Stale context epoch (wall-clock check).

    Expected: BLOCK from actual HTTP service (HTTP 400).
    """
    authority = create_test_authority(authority_id="test-auth-001")
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent()

    # Use stale context epoch (older than MAX_CONTEXT_AGE_SECONDS)
    stale_epoch = int(time.time()) - 400  # 400 seconds ago (MAX is 300)

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=stale_epoch,
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 400"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 400
        assert "stale" in e.response.json()["detail"].lower() or "age" in e.response.json()["detail"].lower()


def test_service_level_future_context(client):
    """
    Service-level test: Future-dated context epoch.

    Expected: BLOCK from actual HTTP service (HTTP 400).
    """
    authority = create_test_authority(authority_id="test-auth-001")
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent()

    # Use future context epoch
    future_epoch = int(time.time()) + 400  # 400 seconds in future

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=future_epoch,
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 400"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 400
        assert "future" in e.response.json()["detail"].lower()


def test_service_level_missing_evidence_with_aee(client):
    """
    Service-level test: AEE conditions present but no evidence envelopes.

    Expected: BLOCK from actual HTTP service (HTTP 400).
    """
    authority = create_test_authority(authority_id="test-auth-001")
    # Keep AEE conditions (requires evidence)
    intent = create_test_intent()

    # No evidence_envelopes provided (but AEE conditions require evidence)

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None  # Missing
        )
        assert False, "Should have raised HTTP 400"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 400
        assert "evidence" in e.response.json()["detail"].lower()


def test_service_level_stale_evidence(client):
    """
    Service-level test: Stale evidence envelope.

    Expected: BLOCK from actual HTTP service (HTTP 400).
    """
    authority = create_test_authority(authority_id="test-auth-001")
    intent = create_test_intent()

    # Create stale evidence envelope (old observed_at)
    stale_envelope = _golden_observer_envelope()
    stale_envelope["observed_at"] = "2020-01-01T00:00:00Z"  # Very old

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=[stale_envelope]
        )
        assert False, "Should have raised HTTP 400"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 400
        # The error could be stale evidence or validation failure
        assert "stale" in e.response.json()["detail"].lower() or "validation" in e.response.json()["detail"].lower() or "freshness" in e.response.json()["detail"].lower()


def test_service_level_invalid_status(client):
    """
    Service-level test: Authority with invalid status.

    Expected: BLOCK from actual HTTP service (HTTP 422 validation error).
    """
    authority = create_test_authority(authority_id="test-auth-001")
    authority["status"] = "INVALID"  # Only VALID is accepted
    authority["aee_conditions"] = None  # No AEE conditions
    intent = create_test_intent()

    try:
        result = client.evaluate(
            authority=authority,
            intent=intent,
            context_epoch=int(time.time()),
            evidence_envelopes=None
        )
        assert False, "Should have raised HTTP 422"
    except requests.exceptions.HTTPError as e:
        assert e.response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
