"""Run the Node issuer client against a real local issuer HTTP process.

All Ed25519 keys are generated for this run and are never written to disk.
Set COMOS_NODE_EXTRACT_PATH when the Node source extract is elsewhere.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ISSUER_DIR = Path(__file__).resolve().parent
NODE_DIR = Path(os.environ.get("COMOS_NODE_EXTRACT_PATH", "/Users/stanislavlevarsky/comos-node-real")).resolve()
NODE_E2E_TEST = NODE_DIR / "src/federation/hub-node-ega-e2e.integration.test.ts"
HUB_DIR = Path(os.environ.get("COMOS_HUB_EXTRACT_PATH", "/Users/stanislavlevarsky/comos-hub-real/extract-hub-a38c768")).resolve()
HUB_TEST = HUB_DIR / "src/federation/brokered-sales-signing-integration.test.ts"
if not NODE_E2E_TEST.is_file():
    raise SystemExit(f"Node integration test not found: {NODE_E2E_TEST}")
if not HUB_TEST.is_file():
    raise SystemExit(f"Hub integration test not found: {HUB_TEST}")

hub_key = Ed25519PrivateKey.generate()
issuer_key = Ed25519PrivateKey.generate()
raw = lambda key: key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
raw_public = lambda key: key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

env = os.environ.copy()
env.update({
    "COMOS_HUB_ACT_PRIVATE_KEY_B64": base64.b64encode(raw(hub_key)).decode("ascii"),
    "COMOS_HUB_ACT_PUBLIC_KEY_B64": base64.b64encode(raw_public(hub_key)).decode("ascii"),
    "COMOS_ISSUER_PRIVATE_KEY_B64": base64.b64encode(raw(issuer_key)).decode("ascii"),
    "COMOS_ISSUER_SCOPE_JSON": json.dumps({
        "allowed_tenants": ["vendor-1"],
        "allowed_products": ["p-1"],
        "allowed_principals": ["buyer-1"],
        "allowed_environments": ["test"],
        "max_quantity_per_item": 5,
        "max_total_coms": 1000,
    }),
    "COMOS_ISSUER_TTL_SECONDS": "120",
    "COMOS_ISSUER_HOST": "127.0.0.1",
    "COMOS_ISSUER_PORT": str(port),
    "EGA_REAL_ISSUER_URL": f"http://127.0.0.1:{port}",
    "EGA_TEST_ISSUER_PUBLIC_KEY_B64": base64.b64encode(raw_public(issuer_key)).decode("ascii"),
})
python = Path(sys.executable)
issuer = subprocess.Popen([str(python), str(ISSUER_DIR / "issuer.py")], cwd=ISSUER_DIR, env=env, stdout=subprocess.DEVNULL, stderr=sys.stderr)
try:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if issuer.poll() is not None:
            raise RuntimeError(f"issuer process exited early with status {issuer.returncode}")
        try:
            with urllib.request.urlopen(f"{env['EGA_REAL_ISSUER_URL']}/health", timeout=0.5) as response:
                if response.status == 200:
                    break
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    else:
        raise RuntimeError("issuer process did not become healthy")

    with tempfile.TemporaryDirectory(prefix="comos-issuer-test-") as scratch:
        env["COMOS_TEST_ACT_OUTPUT"] = str(Path(scratch) / "hub-act.json")
        result = subprocess.run(["npm", "run", "test:signing"], cwd=HUB_DIR, env=env, check=False)
        if result.returncode:
            raise SystemExit(result.returncode)
        # Preflight the exact Hub fixture through the issuer function before
        # starting the HTTP client leg; no values or keys are printed.
        sys.path.insert(0, str(ISSUER_DIR))
        from issuer import IssueRequest, NodePricing, issue_authority
        os.environ.update(env)
        fixture = json.loads(Path(env["COMOS_TEST_ACT_OUTPUT"]).read_text())
        request = IssueRequest(
            act=fixture["payload"], act_signature=fixture["act_signature"],
            node_pricing=NodePricing(items=[{"product_id": "p-1", "unit_price_coms": 125}], total_coms=250),
            principal="buyer-1", environment="test",
        )
        issue_authority(request, scope=json.loads(env["COMOS_ISSUER_SCOPE_JSON"]), private_key=issuer_key)
        result = subprocess.run(["npm", "run", "test:e2e-queue"], cwd=NODE_DIR, env=env, check=False)
        if result.returncode:
            raise SystemExit(result.returncode)
        result = subprocess.run(["npm", "run", "test:issuer"], cwd=NODE_DIR, env=env, check=False)
        raise SystemExit(result.returncode)
finally:
    issuer.terminate()
    try:
        issuer.wait(timeout=5)
    except subprocess.TimeoutExpired:
        issuer.kill()
        issuer.wait(timeout=5)
