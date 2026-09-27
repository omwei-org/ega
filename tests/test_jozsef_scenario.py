import pytest

from ega.authority import AuthorizationError, issue_authority
from ega.boundary import commit, final_authority_check, prepare
from ega.models import AuthorizationScope, RuntimeIntent


def test_substituted_path_is_outside_execution_authority():
    allowed = RuntimeIntent(
        principal="agent-123",
        action="execute",
        target="task-001",
        parameters={"path": "A"},
        environment="runtime-1",
        decision_ref="human-constraint-001",
        governance_context={"instruction": "A-only; stop if unavailable"},
        evidence={"source": "raig-1"},
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="execute",
        target="task-001",
        environment="runtime-1",
        parameter_constraints={"path": "A"},
    )

    authority = issue_authority(allowed, scope, authority_id="authority-a")
    prepared = prepare(authority, context_epoch=1)

    substitute = RuntimeIntent(
        principal="agent-123",
        action="execute",
        target="task-001",
        parameters={"path": "B"},
        environment="runtime-1",
        decision_ref="human-constraint-001",
    )

    with pytest.raises(AuthorizationError):
        issue_authority(substitute, scope, authority_id="authority-b")

    assert prepared.authority.source_decision == "human-constraint-001"
    assert prepared.authority.governance_context["instruction"] == "A-only; stop if unavailable"
    assert final_authority_check(prepared, current_epoch=1) == "VALID"
    assert commit(prepared, current_epoch=1) == {
        "decision": "COMMIT",
        "reason": "VALID",
        "applied": True,
        "effect": "NOT_EXECUTED",
    }


def test_path_a_unavailable_does_not_authorize_path_b():
    intent = RuntimeIntent(
        principal="agent-123",
        action="execute",
        target="task-001",
        parameters={"path": "A"},
        environment="runtime-1",
        decision_ref="human-constraint-001",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="execute",
        target="task-001",
        environment="runtime-1",
        parameter_constraints={"path": "A"},
    )

    authority = issue_authority(intent, scope, authority_id="authority-a")
    prepared = prepare(authority, context_epoch=1)

    # The relevant runtime condition changed after PREPARE. A technically
    # available substitute path is not represented by the prepared authority.
    result = commit(prepared, current_epoch=2)

    assert final_authority_check(prepared, current_epoch=2) == "STALE_CONTEXT"
    assert result == {
        "decision": "BLOCK",
        "reason": "STALE_CONTEXT",
        "applied": False,
        "effect": "NONE",
    }
