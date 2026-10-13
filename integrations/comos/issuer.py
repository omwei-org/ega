"""Operator-controlled ComOS authority issuer (prototype; separate process).

Accepts ACT + node pricing, validates operator-configured scope, recomputes
the canonical action digest, and signs an EGA-compatible Ed25519 authority.
Do not import this process into the node runtime.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

AUDIENCE = os.getenv("EGA_SERVICE_AUDIENCE", "ega-service")
AUTHORITY_ID = os.getenv("COMOS_ISSUER_AUTHORITY_ID", "comos-operator-issuer")
TTL_SECONDS = int(os.getenv("COMOS_ISSUER_TTL_SECONDS", "120"))


class NodePricingItem(BaseModel):
    product_id: str = Field(min_length=1)
    unit_price_coms: int = Field(ge=0)


class NodePricing(BaseModel):
    items: list[NodePricingItem] = Field(min_length=1)
    total_coms: int = Field(ge=0)


class IssueRequest(BaseModel):
    act: dict[str, Any]
    node_pricing: NodePricing
    principal: str = Field(min_length=1)
    environment: str = Field(min_length=1)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def action_digest(act: dict[str, Any], pricing: NodePricing) -> str:
    if act.get("kind") != "retail_sale":
        raise ValueError("unsupported ACT kind")
    for field in ("command_id", "tenant_id"):
        if not isinstance(act.get(field), str) or not act[field].strip():
            raise ValueError(f"ACT {field} is required")
    items = act.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("ACT items must be a non-empty list")
    if len(items) != len(pricing.items):
        raise ValueError("pricing item count does not match ACT")
    total = 0
    for act_item, price_item in zip(items, pricing.items, strict=True):
        if not isinstance(act_item, dict):
            raise ValueError("invalid ACT item")
        product_id, quantity = act_item.get("product_id"), act_item.get("quantity")
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("invalid product_id")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if product_id != price_item.product_id:
            raise ValueError("pricing product/order does not match ACT")
        total += quantity * price_item.unit_price_coms
    if total != pricing.total_coms:
        raise ValueError("node pricing total does not equal unit prices × quantities")
    projection = {
        "schema": "comos-action-digest-v1",
        "act": act,
        "node_pricing": pricing.model_dump(mode="json"),
    }
    return hashlib.sha256(canonical_json(projection)).hexdigest()


def load_scope() -> dict[str, Any]:
    raw = os.getenv("COMOS_ISSUER_SCOPE_JSON", "")
    if not raw:
        raise RuntimeError("COMOS_ISSUER_SCOPE_JSON is required; issuer fails closed")
    try:
        scope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("COMOS_ISSUER_SCOPE_JSON is invalid") from exc
    required = ("allowed_tenants", "allowed_products", "allowed_principals",
                "max_quantity_per_item", "max_total_coms")
    if not isinstance(scope, dict) or any(key not in scope for key in required):
        raise RuntimeError("issuer scope is incomplete")
    if not all(isinstance(scope[k], list) and scope[k] for k in required[:3]):
        raise RuntimeError("allowed scope lists must be non-empty")
    for field in ("max_quantity_per_item", "max_total_coms"):
        if isinstance(scope[field], bool) or not isinstance(scope[field], int) or scope[field] < 0:
            raise RuntimeError(f"{field} must be a non-negative integer")
    return scope


def load_private_key() -> Ed25519PrivateKey:
    raw = os.getenv("COMOS_ISSUER_PRIVATE_KEY_B64", "")
    if not raw:
        raise RuntimeError("COMOS_ISSUER_PRIVATE_KEY_B64 is required; issuer fails closed")
    try:
        key_bytes = base64.b64decode(raw, validate=True)
        if len(key_bytes) != 32:
            raise ValueError("raw Ed25519 private key must be 32 bytes")
        return Ed25519PrivateKey.from_private_bytes(key_bytes)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("COMOS_ISSUER_PRIVATE_KEY_B64 is invalid") from exc


def issue_authority(request: IssueRequest, *, scope: dict[str, Any],
                    private_key: Ed25519PrivateKey,
                    now: datetime | None = None) -> dict[str, Any]:
    act = request.act
    if act.get("kind") != "retail_sale":
        raise ValueError("unsupported ACT kind")
    command_id, tenant_id = act.get("command_id"), act.get("tenant_id")
    if not isinstance(command_id, str) or not command_id.strip() or len(command_id) > 256:
        raise ValueError("invalid command_id")
    if tenant_id not in scope["allowed_tenants"]:
        raise ValueError("tenant outside issuer scope")
    if request.principal not in scope["allowed_principals"]:
        raise ValueError("principal outside issuer scope")
    items = act.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("ACT items must be a non-empty list")
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid ACT item")
        product_id, quantity = item.get("product_id"), item.get("quantity")
        if product_id not in scope["allowed_products"]:
            raise ValueError("product outside issuer scope")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if quantity > scope["max_quantity_per_item"]:
            raise ValueError("quantity exceeds issuer scope")
        normalized_items.append({"product_id": product_id, "quantity": quantity})
    digest = action_digest(act, request.node_pricing)
    if request.node_pricing.total_coms > scope["max_total_coms"]:
        raise ValueError("total exceeds issuer scope")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("issuer clock must be timezone-aware")
    if not 1 <= TTL_SECONDS <= 300:
        raise ValueError("COMOS_ISSUER_TTL_SECONDS must be between 1 and 300")
    issued = current.astimezone(timezone.utc).replace(microsecond=0)
    expires = issued + timedelta(seconds=TTL_SECONDS)
    authority: dict[str, Any] = {
        "authority_id": AUTHORITY_ID,
        "principal": request.principal,
        "action": "retail_sale",
        "target": tenant_id,
        "parameters": {
            "items": normalized_items,
            "expected_total_coms": request.node_pricing.total_coms,
            "command_id": command_id,
            "action_digest": digest,
        },
        "environment": request.environment,
        "source_decision": f"issuer:{command_id}",
        "signature": None,
        "nonce": secrets.token_urlsafe(24),
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "audience": AUDIENCE,
        "governance_context": None,
        "evidence": None,
        "status": "VALID",
        "ao_ref": None,
        "aee_ref": None,
        "ect_ref": None,
        "decision_record_ref": None,
        "decision_record_digest": None,
        "aee_conditions": None,
    }
    authority["signature"] = base64.b64encode(
        private_key.sign(canonical_json(authority))
    ).decode("ascii")
    return authority


app = FastAPI(title="ComOS Operator Authority Issuer", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    load_scope()
    load_private_key()
    return {"status": "ok"}


@app.post("/v1/authority")
def issue_endpoint(request: IssueRequest) -> dict[str, Any]:
    try:
        return issue_authority(request, scope=load_scope(), private_key=load_private_key())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=403, detail="Authority issuance denied") from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("COMOS_ISSUER_HOST", "127.0.0.1"),
                port=int(os.getenv("COMOS_ISSUER_PORT", "8091")))
