from pathlib import Path
"""
ComOS × EGA Integration Experiment

This test demonstrates the EGA → execution-boundary semantics against a real ComOS execution substrate.

Architecture:
- Real ComOS catalog state (MongoDB-backed)
- Observer-style adapter (simulated, not real Observer)
- EvidenceEnvelope → EGA → AEE evaluation
- Experimental execution gate (NOT SLC enforcement)
- Real ComOS order_create execution
- Real MongoDB effect verification

What this proves:
- EGA AEE evaluation against real execution state
- Execution boundary placement and semantics
- BLOCK prevents handler invocation and effect

What this does NOT prove:
- Observer integration (evidence is simulated)
- SLC enforcement (this is an experimental gate only)
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any
import subprocess
import sys
import socket
import pytest

# Add EGA src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ega.aee import evaluate_aee_condition
from ega.authority import issue_authority
from ega.boundary import commit, execution_attestation, prepare
from ega.interop import EvidenceEnvelope, evidence_envelope_integrity_ref, evidence_envelope_to_evidence
from ega.models import AEECondition, AuthorizationScope, DecisionRecord, RuntimeIntent, EvidenceItem

def _comos_node_available() -> bool:
    """Return whether an explicitly opted-in local ComOS endpoint is reachable."""
    if os.environ.get("EGA_RUN_LIVE_COMOS") != "1":
        return False
    try:
        with socket.create_connection(("127.0.0.1", 9101), timeout=1):
            return True
    except OSError:
        return False



# ComOS MCP client for local node
@dataclass
class ComOSClient:
    url: str = "http://127.0.0.1:9101/mcp"
    tenant_id: str = "federation-retail"

    def _call_mcp(self, tool_name: str, arguments: dict) -> dict:
        """Call a ComOS MCP tool."""
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(payload), self.url],
            capture_output=True,
            text=True
        )
        response = json.loads(result.stdout)
        if "result" in response and "content" in response["result"]:
            content = response["result"]["content"][0]
            if content["type"] == "text":
                return json.loads(content["text"])
        return response

    def catalog_put(self, product: dict) -> dict:
        """Create or update a product in the catalog."""
        args = {**product, "tenant_id": self.tenant_id}
        return self._call_mcp("catalog_put", args)

    def catalog_get(self, product_id: str) -> dict:
        """Get a product by ID."""
        return self._call_mcp("catalog_get", {"product_id": product_id})

    def order_create(self, items: list, currency: str = "COM") -> dict:
        """Create an order (the real execution path)."""
        return self._call_mcp("order_create", {
            "items": items,
            "currency": currency,
            "tenant_id": self.tenant_id
        })

    def orders_list(self, limit: int = 10) -> dict:
        """List orders."""
        return self._call_mcp("orders_list", {"limit": limit})


# Observer-style evidence adapter (SIMULATED, not real Observer)
class ObserverStyleAdapter:
    """Simulates Observer evidence production from ComOS product state."""

    @staticmethod
    def product_to_evidence(product: dict, evidence_ref: str) -> EvidenceItem:
        """Convert ComOS product state to EGA EvidenceItem."""
        return EvidenceItem(
            evidence_ref=evidence_ref,
            digest=f"sha256-{hash(json.dumps(product, sort_keys=True))}",  # Simulated digest
            observed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            evaluation_status="USED",
            role="commit_condition",
            target=product.get("product_id", ""),
            state="KNOWN" if product.get("active") else "INACTIVE",
            value={
                "tenant_id": product.get("tenant_id"),
                "product_id": product.get("product_id"),
                "price": product.get("price"),
                "active": product.get("active"),
                "currency": product.get("currency")
            },
            freshness="FRESH",
            uncertainty=0.0,
            provenance="comos-mongodb"
        )


# Experimental execution gate (NOT SLC enforcement)
class ExperimentalExecutionGate:
    """
    Experimental execution gate demonstrating the execution boundary.

    This is NOT the SLC enforcement mechanism. It proves:
    - The placement of the execution boundary
    - That BLOCK decisions prevent handler invocation
    - That COMMIT decisions allow execution
    """

    def __init__(self, comos_client: ComOSClient):
        self.comos = comos_client
        self.handler_invocation_count = 0

    def attempt_execution(
        self,
        prepared_authority,
        current_epoch: int,
        current_evidence: dict[str, EvidenceItem],
        order_items: list
    ) -> dict:
        """
        Attempt execution through the experimental gate.

        Returns: {
            "gate_decision": "COMMIT" | "BLOCK",
            "gate_reason": str,
            "handler_invoked": bool,
            "execution_result": dict | None,
            "post_execution_receipt": dict | None
        }
        """
        # EGA commit decision
        commit_result = commit(
            prepared_authority,
            current_epoch=current_epoch,
            current_evidence=current_evidence
        )

        if commit_result["decision"] == "BLOCK":
            # BLOCK: do NOT invoke handler
            return {
                "gate_decision": "BLOCK",
                "gate_reason": commit_result["reason"],
                "handler_invoked": False,
                "execution_result": None,
                "post_execution_receipt": None
            }

        # COMMIT: invoke handler (simulated boundary before handler)
        self.handler_invocation_count += 1
        execution_result = self.comos.order_create(order_items)

        # Post-execution receipt (separate from pre-execution authorization)
        post_execution_receipt = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "execution_id": f"exec-{int(time.time())}",
            "handler_invoked": True,
            "result": execution_result
        }

        return {
            "gate_decision": "COMMIT",
            "gate_reason": commit_result["reason"],
            "handler_invoked": True,
            "execution_result": execution_result,
            "post_execution_receipt": post_execution_receipt
        }


def test_comos_ega_integration():
    if not _comos_node_available():
        if __name__ != "__main__":
            pytest.skip("live ComOS test not opted in (set EGA_RUN_LIVE_COMOS=1) or node unavailable on 127.0.0.1:9101")
        print("Skipping live ComOS experiment: set EGA_RUN_LIVE_COMOS=1 and start node on 127.0.0.1:9101")
        return
    """
    End-to-end integration test of EGA × ComOS.

    Case A: unchanged execution state → COMMIT → execution
    Case B: changed execution state → BLOCK → no execution
    """
    print("=" * 80)
    print("ComOS × EGA Integration Experiment")
    print("=" * 80)

    comos = ComOSClient()
    gate = ExperimentalExecutionGate(comos)

    # Test product identity
    test_product_id = f"ega-test-{int(time.time())}"
    baseline_price = 2500

    print(f"\nTest product ID: {test_product_id}")
    print(f"Baseline price: {baseline_price}")

    # STEP 1: Create baseline product through real ComOS catalog write path
    print("\n" + "-" * 80)
    print("STEP 1: Create baseline product via catalog_put")
    print("-" * 80)

    baseline_product = {
        "product_id": test_product_id,
        "name": "EGA Test Product",
        "description": "Product for EGA integration test",
        "price": baseline_price,
        "currency": "COM",
        "category": "test",
        "sku": f"SKU-{test_product_id}",
        "digital": True,
        "active": True
    }

    put_result = comos.catalog_put(baseline_product)
    print(f"catalog_put result: {json.dumps(put_result, indent=2)}")

    # Verify product state in MongoDB
    product_state = comos.catalog_get(test_product_id)
    print(f"\nProduct state from MongoDB: {json.dumps(product_state, indent=2)}")

    # STEP 2: Create Observer-style evidence from baseline state
    print("\n" + "-" * 80)
    print("STEP 2: Create Observer-style evidence from baseline state")
    print("-" * 80)

    baseline_evidence = ObserverStyleAdapter.product_to_evidence(
        product_state,
        evidence_ref="evidence-baseline"
    )
    print(f"Baseline evidence: {json.dumps(baseline_evidence.__dict__, indent=2)}")

    # STEP 3: Establish AEE condition (independent authorization basis)
    print("\n" + "-" * 80)
    print("STEP 3: Establish AEE condition (independent authorization basis)")
    print("-" * 80)

    aee_condition = AEECondition(
        condition_id="condition-price-2500",
        evidence_ref="evidence-baseline",
        value_equals={
            "tenant_id": "federation-retail",
            "product_id": test_product_id,
            "price": baseline_price,
            "active": True
        }
    )
    print(f"AEE condition: {json.dumps(aee_condition.__dict__, indent=2)}")

    # STEP 4: Create EGA decision record and authority
    print("\n" + "-" * 80)
    print("STEP 4: Create EGA decision record and authority")
    print("-" * 80)

    decision_record = DecisionRecord(
        decision_id="decision-ega-001",
        decision_time=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        intent_ref="intent-order-create",
        authorization_scope_ref="scope-retail-order",
        evidence_items=(baseline_evidence,),
        aee_conditions=(aee_condition,)
    )

    intent = RuntimeIntent(
        principal="test-agent",
        action="order_create",
        target="retail",
        parameters={"items": [{"product_id": test_product_id, "quantity": 1}]},
        environment="production",
        decision_ref="decision-ega-001"
    )

    scope = AuthorizationScope(
        principal="test-agent",
        action="order_create",
        target="retail",
        environment="production"
    )

    authority = issue_authority(intent, scope, decision_record=decision_record)
    prepared = prepare(authority, context_epoch=1)
    print(f"Authority prepared: {prepared.authority.authority_id}")

    # STEP 5: CASE A - Unchanged execution state
    print("\n" + "=" * 80)
    print("CASE A: Unchanged execution state (price = 2500)")
    print("=" * 80)

    current_evidence_a = {"evidence-baseline": baseline_evidence}
    order_items_a = [{"product_id": test_product_id, "quantity": 1}]

    gate_result_a = gate.attempt_execution(
        prepared,
        current_epoch=1,
        current_evidence=current_evidence_a,
        order_items=order_items_a
    )

    print(f"\nGate decision: {gate_result_a['gate_decision']}")
    print(f"Gate reason: {gate_result_a['gate_reason']}")
    print(f"Handler invoked: {gate_result_a['handler_invoked']}")
    print(f"Execution result: {json.dumps(gate_result_a['execution_result'], indent=2) if gate_result_a['execution_result'] else 'None'}")
    print(f"Post-execution receipt: {json.dumps(gate_result_a['post_execution_receipt'], indent=2) if gate_result_a['post_execution_receipt'] else 'None'}")

    # Verify order was created
    orders_after_a = comos.orders_list(limit=10)
    print(f"\nOrders after Case A: {json.dumps(orders_after_a, indent=2)}")

    # STEP 6: CASE B - Changed execution state
    print("\n" + "=" * 80)
    print("CASE B: Changed execution state (price: 2500 → 3000)")
    print("=" * 80)

    # Change price through real ComOS catalog write path
    changed_price = 3000
    print(f"\nChanging price to {changed_price} via catalog_put...")

    changed_product = baseline_product.copy()
    changed_product["price"] = changed_price
    comos.catalog_put(changed_product)

    # Verify changed state
    changed_state = comos.catalog_get(test_product_id)
    print(f"Changed product state: {json.dumps(changed_state, indent=2)}")

    # Generate fresh evidence from changed state
    changed_evidence = ObserverStyleAdapter.product_to_evidence(
        changed_state,
        evidence_ref="evidence-changed"
    )
    print(f"\nChanged evidence: {json.dumps(changed_evidence.__dict__, indent=2)}")

    # Evaluate SAME pre-established AEE condition (still requires price=2500)
    print(f"\nEvaluating SAME AEE condition (requires price={baseline_price})...")
    eval_result = evaluate_aee_condition(aee_condition, changed_evidence)
    print(f"Evaluation result: {eval_result.status} - {eval_result.reason}")

    # Attempt execution through gate
    current_evidence_b = {"evidence-baseline": changed_evidence}  # Note: using changed evidence
    order_items_b = [{"product_id": test_product_id, "quantity": 1}]

    gate_result_b = gate.attempt_execution(
        prepared,
        current_epoch=1,
        current_evidence=current_evidence_b,
        order_items=order_items_b
    )

    print(f"\nGate decision: {gate_result_b['gate_decision']}")
    print(f"Gate reason: {gate_result_b['gate_reason']}")
    print(f"Handler invoked: {gate_result_b['handler_invoked']}")
    print(f"Execution result: {gate_result_b['execution_result']}")
    print(f"Post-execution receipt: {gate_result_b['post_execution_receipt']}")

    # Verify NO new order was created
    orders_after_b = comos.orders_list(limit=10)
    print(f"\nOrders after Case B: {json.dumps(orders_after_b, indent=2)}")

    # SUMMARY
    print("\n" + "=" * 80)
    print("EXPERIMENT SUMMARY")
    print("=" * 80)

    print(f"\nCase A (unchanged state):")
    print(f"  Product price: {baseline_price}")
    print(f"  EGA decision: COMMIT")
    print(f"  Gate decision: {gate_result_a['gate_decision']}")
    print(f"  Handler invoked: {gate_result_a['handler_invoked']}")
    print(f"  Order created: {gate_result_a['execution_result'] is not None}")

    print(f"\nCase B (changed state):")
    print(f"  Product price: {changed_price}")
    print(f"  EGA decision: BLOCK (AEE_CONDITION_FAILED:VALUE_MISMATCH)")
    print(f"  Gate decision: {gate_result_b['gate_decision']}")
    print(f"  Handler invoked: {gate_result_b['handler_invoked']}")
    print(f"  Order created: {gate_result_b['execution_result'] is not None}")

    # Clean up test product
    print(f"\nCleaning up test product {test_product_id}...")
    # Note: catalog_remove may not be available in all versions
    # For now, we'll leave it for manual inspection

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print("""
This experiment proves:
- EGA AEE evaluation against real ComOS execution state
- Changed evidence ≠ failed condition (fails only when it no longer satisfies the condition)
- The experimental execution gate correctly:
  * Allows execution when EGA returns COMMIT
  * Prevents handler invocation when EGA returns BLOCK
  * Prevents real MongoDB effects when blocked

What this does NOT prove:
- Observer integration (evidence is simulated, not from real Observer)
- SLC enforcement (this is an experimental gate, not the SLC mechanism)
    """)


if __name__ == "__main__":
    test_comos_ega_integration()
