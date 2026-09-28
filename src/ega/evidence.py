from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any

from .models import DecisionRecord, ExecutionAttestation


def decision_record_digest(record: DecisionRecord) -> str:
    payload = {
        "decision_id": record.decision_id,
        "decision_time": record.decision_time,
        "intent_ref": record.intent_ref,
        "authorization_scope_ref": record.authorization_scope_ref,
        "evidence_items": [
            {
                "evidence_ref": item.evidence_ref,
                "digest": item.digest,
                "observed_at": item.observed_at,
                "evaluation_status": item.evaluation_status,
                "role": item.role,
                "source_confidence": item.source_confidence,
            }
            for item in record.evidence_items
        ],
    }
    return sha256(canonical_json(payload)).hexdigest()



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
    if authority_ref != eatt.authority_id:
        raise ValueError("authority reference does not match execution attestation")
    if not intent_ref:
        raise ValueError("intent_ref is required")
    if not prepared_context_ref:
        raise ValueError("prepared_context_ref is required")
    if not final_check_ref:
        raise ValueError("final_check_ref is required")
    if eatt.decision == "COMMIT" and commit_ref is None:
        raise ValueError("commit_ref is required for COMMIT")
    if eatt.effect != "NONE" and outcome_ref is None:
        raise ValueError("outcome_ref is required when an effect is recorded")

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
