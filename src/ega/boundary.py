from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any
from .models import ExecutionAuthority, ExecutionAttestation

@dataclass(frozen=True)
class PreparedAuthority:
    authority: ExecutionAuthority
    context_epoch: int
    authority_digest: str

def _digest(authority: ExecutionAuthority) -> str:
    payload = {"authority_id": authority.authority_id, "principal": authority.principal, "action": authority.action, "target": authority.target, "parameters": authority.parameters, "environment": authority.environment, "source_decision": authority.source_decision, "status": authority.status}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def prepare(authority: ExecutionAuthority, context_epoch: int) -> PreparedAuthority:
    """Capture authority and execution-context snapshot before commit."""
    if authority.status != "VALID":
        raise ValueError("only VALID execution authority may be prepared")
    return PreparedAuthority(authority, context_epoch, _digest(authority))

def final_authority_check(prepared: PreparedAuthority, current_epoch: int, current_authority: ExecutionAuthority | None = None) -> str:
    """Re-check authority/context immediately before commit."""
    if current_epoch != prepared.context_epoch:
        return "STALE_CONTEXT"
    if current_authority is not None and _digest(current_authority) != prepared.authority_digest:
        return "AUTHORITY_DIGEST_MISMATCH"
    return "VALID"

def commit(prepared: PreparedAuthority, current_epoch: int, current_authority: ExecutionAuthority | None = None) -> dict[str, Any]:
    """Return a commit decision; this seam performs no external effect.\n\n`applied` means the commit decision was accepted by this reference gate;\n`effect` records whether an external effect was actually performed. This\nreference implementation never performs the external effect itself.\n"""
    reason = final_authority_check(prepared, current_epoch, current_authority)
    if reason != "VALID":
        return {"decision": "BLOCK", "reason": reason, "applied": False, "effect": "NONE"}
    return {"decision": "COMMIT", "reason": "VALID", "applied": True, "effect": "NOT_EXECUTED"}


def execution_attestation(prepared: PreparedAuthority, result: dict[str, Any], execution_id: str, current_epoch: int) -> ExecutionAttestation:
    """Create an EAtt/failure record from a boundary decision.

    This records evidence only; it does not attest to tamper resistance or
    independently prove that an external effect occurred.
    """
    if not execution_id:
        raise ValueError("execution_id is required")
    return ExecutionAttestation(
        execution_id=execution_id,
        authority_id=prepared.authority.authority_id,
        authority_digest=prepared.authority_digest,
        prepared_context_epoch=prepared.context_epoch,
        current_context_epoch=current_epoch,
        decision=result["decision"],
        reason=result["reason"],
        commit="ATTEMPTED" if result["decision"] == "COMMIT" else "NOT_ATTEMPTED",
        effect=result["effect"],
        ao_ref=prepared.authority.ao_ref,
        aee_ref=prepared.authority.aee_ref,
        ect_ref=prepared.authority.ect_ref,
    )
