"""Run the TypeScript gate tests against the actual FastAPI EGA service.

The authority bypass is deliberately limited to this isolated test process. It
must never be copied into a real ComOS deployment.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

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
