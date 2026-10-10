"""
State Drift Experiment — EGA Authorization vs ComOS Execution

This experiment demonstrates whether execution-time state can differ from
the state that was authorized by EGA.

Critical difference from test_comos_ega_integration.py:
- The original test regenerates evidence after state change (Case B line 341-345)
- This test KEEPS the original evidence after state change
- This tests whether ComOS uses authorization-time evidence OR execution-time state
"""

from pathlib import Path

import json
import hashlib
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
from ega.boundary import commit, prepare
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
            digest=f"sha256-{hashlib.sha256(json.dumps(product, sort_keys=True, separators=(\",\", \":\")).encode()).hexdigest()}",  # Deterministic test digest, not a signed Observer envelope
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


def test_state_drift():
    if not _comos_node_available():
        if __name__ != "__main__":
            pytest.skip("live ComOS test not opted in (set EGA_RUN_LIVE_COMOS=1) or node unavailable on 127.0.0.1:9101")
        print("Skipping live ComOS experiment: set EGA_RUN_LIVE_COMOS=1 and start node on 127.0.0.1:9101")
        return
    """
    State Drift Experiment:
    1. Authorize with evidence showing price=X
    2. Change actual product state to Y
    3. Execute WITHOUT regenerating evidence
    4. Determine whether execution uses X or Y
    """
    print("=" * 80)
    print("STATE DRIFT EXPERIMENT")
    print("=" * 80)

    comos = ComOSClient()

    # Test product identity
    test_product_id = f"drift-test-{int(time.time())}"
    baseline_price = 2500
    drifted_price = 3000

    print(f"\nTest product ID: {test_product_id}")
    print(f"Baseline price (X): {baseline_price}")
    print(f"Drifted price (Y): {drifted_price}")

    # ============================================================
    # PHASE 1: Create baseline product
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 1: Create baseline product via catalog_put")
    print("=" * 80)

    baseline_product = {
        "product_id": test_product_id,
        "name": "State Drift Test Product",
        "description": "Product for state drift experiment",
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
    product_state_baseline = comos.catalog_get(test_product_id)
    print(f"\nProduct state from MongoDB (baseline): {json.dumps(product_state_baseline, indent=2)}")

    # ============================================================
    # PHASE 2: Create authorization state X
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 2: Create EGA authorization with evidence showing price=X")
    print("=" * 80)

    baseline_evidence = ObserverStyleAdapter.product_to_evidence(
        product_state_baseline,
        evidence_ref="evidence-baseline"
    )
    print(f"\nBaseline evidence (price={baseline_price}):")
    print(json.dumps(baseline_evidence.__dict__, indent=2))

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
    print(f"\nAEE condition (requires price={baseline_price}):")
    print(json.dumps(aee_condition.__dict__, indent=2))

    decision_record = DecisionRecord(
        decision_id="decision-drift-001",
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
        decision_ref="decision-drift-001"
    )

    scope = AuthorizationScope(
        principal="test-agent",
        action="order_create",
        target="retail",
        environment="production"
    )

    authority = issue_authority(intent, scope, decision_record=decision_record)
    prepared = prepare(authority, context_epoch=1)
    print(f"\nAuthority issued: {prepared.authority.authority_id}")
    print(f"Decision record: {decision_record.decision_id}")

    # ============================================================
    # PHASE 3: Verify authorization against X
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 3: Verify final authority check with baseline evidence")
    print("=" * 80)

    current_evidence = {"evidence-baseline": baseline_evidence}
    commit_result = commit(
        prepared,
        current_epoch=1,
        current_evidence=current_evidence
    )
    print(f"\nCommit decision: {commit_result['decision']}")
    print(f"Commit reason: {commit_result['reason']}")

    if commit_result["decision"] != "COMMIT":
        print("\nERROR: Authorization check failed with baseline evidence")
        print("Cannot proceed with state drift experiment")
        return

    # ============================================================
    # PHASE 4: Introduce state drift (X → Y)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 4: Introduce state drift (price: X → Y)")
    print("=" * 80)

    drifted_product = baseline_product.copy()
    drifted_product["price"] = drifted_price

    print(f"\nChanging price from {baseline_price} to {drifted_price} via catalog_put...")
    comos.catalog_put(drifted_product)

    # Verify changed state
    product_state_drifted = comos.catalog_get(test_product_id)
    print(f"\nProduct state from MongoDB (drifted): {json.dumps(product_state_drifted, indent=2)}")

    # CRITICAL: DO NOT regenerate evidence
    # DO NOT update AEE condition
    # DO NOT update authority
    print("\nCRITICAL: Evidence, AEE condition, and authority remain unchanged")
    print(f"Evidence still shows price={baseline_price}")
    print(f"AEE condition still requires price={baseline_price}")
    print(f"Actual product state now has price={drifted_price}")

    # ============================================================
    # PHASE 5: Execute through normal ComOS path
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 5: Execute retail_sale through normal ComOS path")
    print("=" * 80)

    order_items = [{"product_id": test_product_id, "quantity": 1}]
    print(f"\nOrder items: {json.dumps(order_items, indent=2)}")

    # Execute WITHOUT running EGA final check with drifted evidence
    # Use the SAME prepared authority and baseline evidence
    print("\nExecuting with:")
    print(f"  - Authority issued when price={baseline_price}")
    print(f"  - Evidence showing price={baseline_price}")
    print(f"  - Actual product price={drifted_price}")

    execution_result = comos.order_create(order_items)
    print(f"\nExecution result: {json.dumps(execution_result, indent=2)}")

    # ============================================================
    # PHASE 6: Inspect protected effect
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 6: Inspect protected effect")
    print("=" * 80)

    orders = comos.orders_list(limit=1)
    print(f"\nOrders: {json.dumps(orders, indent=2)}")

    if execution_result and "result" in execution_result:
        order = execution_result["result"]
        print(f"\nOrder details:")
        print(f"  Order ID: {order.get('order_id')}")
        print(f"  Status: {order.get('status')}")
        print(f"  Total: {order.get('total')}")
        print(f"  Currency: {order.get('currency')}")

        if "lines" in order:
            for line in order["lines"]:
                print(f"  Line: product_id={line.get('product_id')}, quantity={line.get('quantity')}, unit_price={line.get('unit_price')}")

    # ============================================================
    # VERDICT
    # ============================================================
    print("\n" + "=" * 80)
    print("EXPERIMENT VERDICT")
    print("=" * 80)

    if execution_result and "result" in execution_result:
        order_total = execution_result["result"].get("total")

        print(f"\nObserver authorized X: {baseline_price}")
        print(f"EGA EvidenceItem.value: {baseline_price}")
        print(f"AEE requires: {baseline_price}")
        print(f"Local product state changed to Y: {drifted_price}")
        print(f"ComOS retail_sale executed")
        print(f"Price used by execution: {order_total / 1 if 'lines' in execution_result['result'] else 'N/A'}")
        print(f"Order total: {order_total}")

        if "lines" in execution_result["result"]:
            unit_price = execution_result["result"]["lines"][0].get("unit_price")
            print(f"Unit price used: {unit_price}")

            if unit_price == drifted_price:
                print("\n" + "=" * 80)
                print("CONFIRMED: EFFECT FOLLOWED DRIFTED STATE")
                print("=" * 80)
                print("""
This empirically demonstrates:
- Authorization-time evidence state was X (price=2500)
- Execution-time state was Y (price=3000)
- The protected effect followed Y (order total based on price=3000)
- The EGA authorization/evidence condition was NOT bound to the execution-time state
                """)
            elif unit_price == baseline_price:
                print("\n" + "=" * 80)
                print("CONFIRMED: EFFECT REMAINED BOUND TO AUTHORIZED STATE")
                print("=" * 80)
                print("""
This empirically demonstrates:
- Authorization-time evidence state was X (price=2500)
- Execution-time state was Y (price=3000)
- The protected effect used X (order total based on price=2500)
- Some mechanism carried the authorized value into execution
                """)
            else:
                print("\n" + "=" * 80)
                print(f"INCONCLUSIVE: Unit price {unit_price} does not match X or Y")
                print("=" * 80)
        else:
            print("\nINCONCLUSIVE: Could not determine unit price from order")
    else:
        print("\nINCONCLUSIVE: Execution failed, cannot determine effect")

    # Clean up
    print(f"\nTest product {test_product_id} left for manual inspection")


if __name__ == "__main__":
    test_state_drift()
