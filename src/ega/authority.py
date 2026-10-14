from __future__ import annotations

import math
from typing import Any

from .evidence import authorization_scope_digest, decision_record_digest, runtime_intent_digest
from .models import AuthorizationScope, DecisionRecord, ExecutionAuthority, RuntimeIntent


class AuthorizationError(ValueError):
    """Raised when runtime intent is outside the provisioning-time authorization scope."""


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return True


def _matches_constraint(value: Any, constraint: Any) -> bool:
    if isinstance(constraint, dict):
        if "equals" in constraint:
            expected = constraint["equals"]
            # Reject non-finite numeric values even when an equality constraint
            # happens to contain the same infinity. Never collapse bool/int.
            for candidate in (value, expected):
                if isinstance(candidate, (int, float)) and not _is_finite_number(candidate):
                    return False
            if isinstance(value, bool) != isinstance(expected, bool) or value != expected:
                return False
        for bound_name, comparison in (("min", lambda v, b: v >= b), ("max", lambda v, b: v <= b)):
            if bound_name not in constraint:
                continue
            bound = constraint[bound_name]
            if not _is_finite_number(value) or not _is_finite_number(bound):
                return False
            if not comparison(value, bound):
                return False
        return True
    return value == constraint


def _within_scope(intent: RuntimeIntent, scope: AuthorizationScope) -> bool:
    if (
        intent.principal != scope.principal
        or intent.action != scope.action
        or intent.target != scope.target
        or intent.environment != scope.environment
    ):
        return False

    for name, constraint in scope.parameter_constraints.items():
        if not isinstance(name, str) or not name:
            return False
        if not _matches_constraint(intent.parameters[name], constraint):
            return False
    return True


def issue_authority(
    intent: RuntimeIntent,
    scope: AuthorizationScope,
    authority_id: str = "ega-authority-001",
    *,
    decision_record: DecisionRecord | None = None,
) -> ExecutionAuthority:
    """Issue bounded execution authority and bind it to an EGA decision record."""
    if not intent.principal or not intent.action or not intent.target:
        raise ValueError("principal, action, and target are required")
    if not intent.environment or not intent.decision_ref:
        raise ValueError("environment and decision_ref are required")
    if not scope.principal or not scope.action or not scope.target or not scope.environment:
        raise ValueError("authorization scope is incomplete")
    if not _within_scope(intent, scope):
        raise AuthorizationError("runtime intent is outside authorization scope")

    if decision_record is not None:
        if decision_record.decision_id != intent.decision_ref:
            raise ValueError("decision record does not match runtime intent decision_ref")
        if not decision_record.authorization_scope_ref:
            raise ValueError("decision record authorization_scope_ref is required")
        if intent.intent_ref is not None and decision_record.intent_ref != intent.intent_ref:
            raise ValueError("decision record does not match runtime intent reference")
        if scope.scope_ref is not None and decision_record.authorization_scope_ref != scope.scope_ref:
            raise ValueError("decision record does not match authorization scope reference")
        expected_intent_digest = runtime_intent_digest(intent)
        expected_scope_digest = authorization_scope_digest(scope)
        if decision_record.intent_digest is not None and decision_record.intent_digest != expected_intent_digest:
            raise ValueError("decision record does not match runtime intent digest")
        if decision_record.authorization_scope_digest is not None and decision_record.authorization_scope_digest != expected_scope_digest:
            raise ValueError("decision record does not match authorization scope digest")
        evidence_refs = {item.evidence_ref for item in decision_record.evidence_items}
        if len(evidence_refs) != len(decision_record.evidence_items):
            raise ValueError("decision record contains duplicate evidence references")
        if any(condition.evidence_ref not in evidence_refs for condition in decision_record.aee_conditions):
            raise ValueError("AEE condition references evidence absent from decision record")

    return ExecutionAuthority(
        authority_id=authority_id, principal=intent.principal, action=intent.action,
        target=intent.target, parameters=dict(intent.parameters), environment=intent.environment,
        source_decision=intent.decision_ref, governance_context=dict(intent.governance_context),
        evidence=dict(intent.evidence),
        decision_record_ref=decision_record.decision_id if decision_record else None,
        decision_record_digest=decision_record_digest(decision_record) if decision_record else None,
        aee_conditions=decision_record.aee_conditions if decision_record else (),
    )
