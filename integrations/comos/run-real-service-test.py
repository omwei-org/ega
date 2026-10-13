"""Run the TypeScript gate tests against the actual FastAPI EGA service.

The authority bypass is deliberately limited to this isolated test process. It
must never be copied into a real ComOS deployment.
"""
from __future__ import annotations

import os
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


# Shared canonical-action digest vector: keep aligned with the TypeScript test.
_digest_vector = {
    "schema": "comos-action-digest-v1",
    "act": {
        "kind": "retail_sale",
        "command_id": "cmd-0001",
        "tenant_id": "tenant-vendor-1",
        "items": [{"product_id": "p-1", "quantity": 2}],
        "buyer_root": "buyer-7",
        "payer_tenant_id": "tenant-buyer-7",
        "brokered_sale_id": "sale-0001",
    },
    "node_pricing": {
        "items": [{"product_id": "p-1", "unit_price_coms": 125}],
        "total_coms": 250,
    },
}
_digest_bytes = json.dumps(_digest_vector, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
assert hashlib.sha256(_digest_bytes).hexdigest() == "0341012ba38a25a2be30c22ba24cdf2151d35fcda389c729bc6d1c0c00e5dcff"


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    PORT = sock.getsockname()[1]

os.environ["EGA_ALLOW_UNVERIFIED_AUTHORITY"] = "true"
os.environ["EGA_FAIL_CLOSED"] = "false"
os.environ["EGA_TRUSTED_AUTHORITY_IDS"] = "auth-test"
os.environ["EGA_REPLAY_DB_PATH"] = str(Path(tempfile.gettempdir()) / "ega-ts-real-service-test.sqlite3")
os.environ["EGA_PORT"] = str(PORT)

import uvicorn
from ega import service

service.CONTEXT_VERSION_PROVIDER = lambda _request: 7
server = uvicorn.Server(uvicorn.Config(
    service.app,
    host="127.0.0.1",
    port=PORT,
    log_level="error",
))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()

base_url = f"http://127.0.0.1:{PORT}"
try:
    import urllib.request

    deadline = time.monotonic() + 10
    while True:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                if response.status == 200:
                    break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("EGA service did not become healthy")
            time.sleep(0.1)

    env = os.environ.copy()
    env["EGA_REAL_SERVICE_URL"] = base_url
    result = subprocess.run(
        [
            "node", "--experimental-strip-types", "--test",
            "integrations/comos/ega-http-gate.test.ts",
        ],
        cwd=ROOT,
        env=env,
        check=False,
    )
    raise SystemExit(result.returncode)
finally:
    server.should_exit = True
    thread.join(timeout=5)
