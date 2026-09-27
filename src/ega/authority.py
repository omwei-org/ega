from .models import ExecutionAuthority, RuntimeIntent

def issue_authority(intent: RuntimeIntent, authority_id: str = "ega-authority-001") -> ExecutionAuthority:
    """Issue bounded execution authority from an already-authorized runtime intent.

    This reference implementation deliberately does not execute or commit the action.
    """
    if not intent.principal or not intent.action or not intent.target:
        raise ValueError("principal, action, and target are required")
    if not intent.environment or not intent.decision_ref:
        raise ValueError("environment and decision_ref are required")

    return ExecutionAuthority(
        authority_id=authority_id,
        principal=intent.principal,
        action=intent.action,
        target=intent.target,
        parameters=dict(intent.parameters),
        environment=intent.environment,
        source_decision=intent.decision_ref,
    )
