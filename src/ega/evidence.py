from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any

from .models import ExecutionAttestation


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def evidence_bundle(
    eatt: ExecutionAttestation,
    *,
    intent_ref: str,
    authority_ref: str,
    prepared_context_ref: str,
    final_check_ref: str,
    commit_ref: str | None = None,
    outcome_ref: str | None = None,
) -> dict[str, Any]:
    """Build a minimal deterministic evidence bundle manifest.

    This is a reference correlation container, not a signed attestation
    or proof of an external effect.
    """
    manifest: dict[str, Any] = {
        "version": "0.1",
        "execution_id": eatt.execution_id,
        "execution_attestation": asdict(eatt),
        "references": {
            "intent": intent_ref,
            "authority": authority_ref,
            "prepared_context": prepared_context_ref,
            "final_check": final_check_ref,
            "commit": commit_ref,
            "outcome": outcome_ref,
        },
    }
    payload = canonical_json(manifest)
    manifest["manifest_sha256"] = sha256(payload).hexdigest()
    return manifest
