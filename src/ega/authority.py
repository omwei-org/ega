from typing import Any
from .models import AuthorizationScope, DecisionRecord, ExecutionAuthority, RuntimeIntent
from .boundary import _decision_record_digest

class AuthorizationError(ValueError):
    """Raised when runtime intent is outside the provisioning-time authorization scope."""

def _matches_constraint(value: Any, constraint: Any) -> bool:
    if isinstance(constraint, dict):
        if "equals" in constraint and value != constraint["equals"]:
            return False
        if "min" in constraint and (not isinstance(value, (int, float)) or value < constraint["min"]):
            return False
        if "max" in constraint and (not isinstance(value, (int, float)) or value > constraint["max"]):
            return False
        return True
    return value == constraint

def _within_scope(intent: RuntimeIntent, scope: AuthorizationScope) -> bool:
    if (intent.principal != scope.principal or intent.action != scope.action or
        intent.target != scope.target or intent.environment != scope.environment):
        return False
    for name, constraint in scope.parameter_constraints.items():
        if name not in intent.parameters or not _matches_constraint(intent.parameters[name], constraint):
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
        if decision_record.authorization_scope_ref == "":
            raise ValueError("decision record authorization_scope_ref is required")

    return ExecutionAuthority(
        authority_id=authority_id, principal=intent.principal, action=intent.action,
        target=intent.target, parameters=dict(intent.parameters), environment=intent.environment,
        source_decision=intent.decision_ref, governance_context=dict(intent.governance_context),
        evidence=dict(intent.evidence),
        decision_record_ref=decision_record.decision_id if decision_record else None,
        decision_record_digest=_decision_record_digest(decision_record) if decision_record else None,
    )
