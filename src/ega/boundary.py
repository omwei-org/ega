from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .models import ExecutionAuthority, ExecutionAttestation, DecisionRecord, EvidenceItem
from .evidence import decision_record_digest
from .aee import evaluate_aee_condition

@dataclass(frozen=True)
class PreparedAuthority:
    authority: ExecutionAuthority
    context_epoch: int
    authority_digest: str

def _digest(authority: ExecutionAuthority) -> str:
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
        "aee_conditions": [condition.__dict__ for condition in authority.aee_conditions],
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def prepare(authority: ExecutionAuthority, context_epoch: int) -> PreparedAuthority:
    if authority.status != "VALID":
        raise ValueError("only VALID execution authority may be prepared")
    return PreparedAuthority(authority, context_epoch, _digest(authority))

def final_authority_check(
    prepared: PreparedAuthority,
    current_epoch: int,
    current_authority: ExecutionAuthority | None = None,
    current_evidence: dict[str, EvidenceItem] | None = None,
) -> str:
    """Re-check authority and EGA-defined AEE predicates immediately before commit.

    AEE conditions are the single authority-side representation of the declared
    commit predicates. Evidence identity/integrity remains in EvidenceItem and
    DecisionRecord; a changed digest does not fail a predicate unless its
    semantic value no longer satisfies the condition.
    """
    if current_epoch != prepared.context_epoch:
        return "STALE_CONTEXT"

    if current_evidence is not None and prepared.authority.aee_conditions:
        for condition in prepared.authority.aee_conditions:
            evidence = current_evidence.get(condition.evidence_ref)
            if evidence is None:
                return "AEE_EVIDENCE_UNAVAILABLE"
            result = evaluate_aee_condition(condition, evidence)
            if result.status != "VALID":
                return f"AEE_CONDITION_FAILED:{result.reason}"

    if current_authority is not None and _digest(current_authority) != prepared.authority_digest:
        return "AUTHORITY_DIGEST_MISMATCH"
    return "VALID"

def commit(
    prepared: PreparedAuthority,
    current_epoch: int,
    current_authority: ExecutionAuthority | None = None,
    current_evidence: dict[str, EvidenceItem] | None = None,
) -> dict[str, Any]:
    reason = final_authority_check(
        prepared, current_epoch, current_authority, current_evidence
    )
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
        if set(selected_evidence_refs) - known_evidence_refs:
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
