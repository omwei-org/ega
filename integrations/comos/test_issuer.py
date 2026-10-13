import base64
import os
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from issuer import IssueRequest, NodePricing, action_digest, canonical_json, issue_authority


def fixture_data():
    hub_key = Ed25519PrivateKey.generate()
    issuer_key = Ed25519PrivateKey.generate()
    os.environ["COMOS_HUB_ACT_PUBLIC_KEY_B64"] = base64.b64encode(hub_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    act = {
        "kind": "retail_sale",
        "command_id": "cmd-0001",
        "tenant_id": "tenant-vendor-1",
        "items": [{"product_id": "p-1", "quantity": 2}],
        "buyer_root": "buyer-7",
        "payer_tenant_id": "tenant-buyer-7",
        "brokered_sale_id": "sale-0001",
    }
    pricing = NodePricing(items=[{"product_id": "p-1", "unit_price_coms": 125}], total_coms=250)
    request = IssueRequest(
        act=act,
        act_signature=base64.b64encode(hub_key.sign(canonical_json(act))).decode(),
        node_pricing=pricing,
        principal="buyer-7",
        environment="test",
    )
    scope = {
        "allowed_tenants": ["tenant-vendor-1"],
        "allowed_products": ["p-1"],
        "allowed_principals": ["buyer-7"],
        "max_quantity_per_item": 5,
        "max_total_coms": 1000,
    }
    return hub_key, issuer_key, request, scope


def test_issuer_signs_authority_bound_to_digest():
    _, key, request, scope = fixture_data()
    now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    authority = issue_authority(request, scope=scope, private_key=key, now=now)
    assert authority["parameters"]["action_digest"] == action_digest(request.act, request.node_pricing)
    assert authority["parameters"]["command_id"] == "cmd-0001"


@pytest.mark.parametrize("change", [
    {"allowed_tenants": ["other-tenant"]},
    {"allowed_products": ["other-product"]},
    {"allowed_principals": ["other-buyer"]},
    {"max_quantity_per_item": 1},
    {"max_total_coms": 249},
])
def test_issuer_denies_out_of_scope_action(change):
    _, key, request, scope = fixture_data()
    scope.update(change)
    with pytest.raises(ValueError):
        issue_authority(request, scope=scope, private_key=key)


def test_issuer_rejects_bad_hub_signature():
    _, key, request, scope = fixture_data()
    request = request.model_copy(update={"act_signature": base64.b64encode(b"not a signature").decode()})
    with pytest.raises(ValueError):
        issue_authority(request, scope=scope, private_key=key)


def test_issuer_rejects_price_total_mismatch():
    _, key, request, scope = fixture_data()
    pricing = NodePricing(items=[{"product_id": "p-1", "unit_price_coms": 125}], total_coms=251)
    request = request.model_copy(update={"node_pricing": pricing})
    with pytest.raises(ValueError):
        issue_authority(request, scope=scope, private_key=key)
