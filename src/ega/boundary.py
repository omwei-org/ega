from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any
from .models import ExecutionAuthority, ExecutionAttestation, DecisionRecord
from .evidence import decision_record_digest

@dataclass(frozen=True)
class PreparedAuthority:
    authority: ExecutionAuthority
    context_epoch: int
    authority_digest: str

def _digest(authority: ExecutionAuthority) -> str:
    """Digest all authority fields that affect authorization/commit semantics."""
    payload = {
        "authority_id": authority.authority_id,
        "principal": authority.principal,
        "action": authority.action,
        "target": authority.target,
        "parameters": authority.parameters,
        "environment": authority.environment,
        "source_decision": authority.source_decision,
        "governance_context": authority.governance_context,
        "evidence": authority.evidence,
        "status": authority.status,
        "ao_ref": authority.ao_ref,
        "aee_ref": authority.aee_ref,
        "ect_ref": authority.ect_ref,
        "decision_record_ref": authority.decision_record_ref,
        "decision_record_digest": authority.decision_record_digest,
        "aee_conditions": authority.aee_conditions,
        "aee_condition_digests": authority.aee_condition_digests,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def prepare(authority: ExecutionAuthority, context_epoch: int) -> PreparedAuthority:
    """Capture authority and execution-context snapshot before commit."""
    if authority.status != "VALID":
        raise ValueError("only VALID execution authority may be prepared")
    return PreparedAuthority(authority, context_epoch, _digest(authority))

def final_authority_check(prepared: PreparedAuthority, current_epoch: int, current_authority: ExecutionAuthority | None = None, current_evidence_digests: dict[str, str] | None = None) -> str:
    """Re-check authority/context immediately before commit."""
    if current_epoch != prepared.context_epoch:
        return "STALE_CONTEXT"
    if current_evidence_digests is not None:
        for evidence_ref in prepared.authority.aee_conditions:
            if current_evidence_digests.get(evidence_ref) != prepared.authority.aee_condition_digests.get(evidence_ref):
                return "AEE_CONDITION_FAILED"
    if current_authority is not None and _digest(current_authority) != prepared.authority_digest:
        return "AUTHORITY_DIGEST_MISMATCH"
    return "VALID"

def commit(prepared: PreparedAuthority, current_epoch: int, current_authority: ExecutionAuthority | None = None, current_evidence_digests: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a commit decision; this seam performs no external effect.\n\n`applied` means the commit decision was accepted by this reference gate;\n`effect` records whether an external effect was actually performed. This\nreference implementation never performs the external effect itself.\n"""
    reason = final_authority_check(prepared, current_epoch, current_authority, current_evidence_digests)
    if reason != "VALID":
        return {"decision": "BLOCK", "reason": reason, "applied": False, "effect": "NONE"}
    return {"decision": "COMMIT", "reason": "VALID", "applied": True, "effect": "NOT_EXECUTED"}



def execution_attestation(
    prepared: PreparedAuthority,
    result: dict[str, Any],
    execution_id: str,
    current_epoch: int,
    *,
    decision_record: DecisionRecord | None = None,
    selected_evidence_refs: tuple[str, ...] = (),
) -> ExecutionAttestation:
    """Create an EAtt/failure record from a boundary decision.

    This records evidence only; it does not attest to tamper resistance or
    independently prove that an external effect occurred.
    """
    if not execution_id:
        raise ValueError("execution_id is required")

    authority = prepared.authority
    if decision_record is not None:
        record_digest = decision_record_digest(decision_record)
        if authority.decision_record_ref != decision_record.decision_id:
            raise ValueError("decision record does not match prepared authority")
        if authority.decision_record_digest != record_digest:
            raise ValueError("decision record digest does not match prepared authority")
        known_evidence_refs = {item.evidence_ref for item in decision_record.evidence_items}
        unknown_refs = set(selected_evidence_refs) - known_evidence_refs
        if unknown_refs:
            raise ValueError("selected evidence reference is not present in decision record")
        decision_record_ref = decision_record.decision_id
        decision_record_digest_value = record_digest
    else:
        if selected_evidence_refs:
            raise ValueError("selected evidence references require a decision record")
        decision_record_ref = authority.decision_record_ref
        decision_record_digest_value = authority.decision_record_digest

    return ExecutionAttestation(
        execution_id=execution_id,
        authority_id=authority.authority_id,
        authority_digest=prepared.authority_digest,
        prepared_context_epoch=prepared.context_epoch,
        current_context_epoch=current_epoch,
        decision=result["decision"],
        reason=result["reason"],
        commit="ATTEMPTED" if result["decision"] == "COMMIT" else "NOT_ATTEMPTED",
        effect=result["effect"],
        ao_ref=authority.ao_ref,
        aee_ref=authority.aee_ref,
        ect_ref=authority.ect_ref,
        decision_record_ref=decision_record_ref,
        decision_record_digest=decision_record_digest_value,
        selected_evidence_refs=tuple(selected_evidence_refs),
    )
