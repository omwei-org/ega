from ega.authority import issue_authority
from ega.boundary import commit, final_authority_check, prepare
from ega.models import AuthorizationScope, RuntimeIntent

def authority():
    intent = RuntimeIntent(principal="agent-123", action="open", target="valve-v1", parameters={"value": 20}, environment="plant-7", decision_ref="raig-784")
    scope = AuthorizationScope(principal="agent-123", action="open", target="valve-v1", environment="plant-7", parameter_constraints={"value": {"min": 0, "max": 20}})
    return issue_authority(intent, scope)

def test_prepare_then_commit():
    prepared = prepare(authority(), context_epoch=1)
    assert final_authority_check(prepared, current_epoch=1) == "VALID"
    assert commit(prepared, current_epoch=1) == {"decision": "COMMIT", "reason": "VALID", "applied": True, "effect": "NOT_EXECUTED"}

def test_epoch_change_blocks_commit():
    prepared = prepare(authority(), context_epoch=1)
    assert final_authority_check(prepared, current_epoch=2) == "STALE_CONTEXT"
    assert commit(prepared, current_epoch=2) == {"decision": "BLOCK", "reason": "STALE_CONTEXT", "applied": False, "effect": "NONE"}

def test_authority_change_blocks_commit():
    original = authority()
    prepared = prepare(original, context_epoch=1)
    changed = type(original)(**{**original.__dict__, "parameters": {"value": 19}})
    assert final_authority_check(prepared, current_epoch=1, current_authority=changed) == "AUTHORITY_DIGEST_MISMATCH"
