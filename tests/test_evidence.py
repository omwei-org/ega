from dataclasses import replace

from ega.authority import issue_authority
from ega.boundary import commit, prepare
from ega.evidence import canonical_json, evidence_bundle
from ega.models import AuthorizationScope, RuntimeIntent


def make_authority():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": 20},
        environment="plant-7",
        decision_ref="raig-784",
    )
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )
    return issue_authority(intent, scope)


def test_evidence_bundle_is_deterministic():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=1)
    from ega.boundary import execution_attestation

    eatt = execution_attestation(
        prepared, result, execution_id="exec-001", current_epoch=1
    )
    kwargs = dict(
        intent_ref="intent-001",
        authority_ref=prepared.authority.authority_id,
        prepared_context_ref="ctx-001",
        final_check_ref="check-001",
        commit_ref="commit-001",
    )
    assert canonical_json(evidence_bundle(eatt, **kwargs)) == canonical_json(
        evidence_bundle(eatt, **kwargs)
    )


def test_evidence_bundle_preserves_negative_boundary_result():
    prepared = prepare(make_authority(), context_epoch=1)
    result = commit(prepared, current_epoch=2)
    from ega.boundary import execution_attestation

    eatt = execution_attestation(
        prepared, result, execution_id="exec-002", current_epoch=2
    )
    bundle = evidence_bundle(
        eatt,
        intent_ref="intent-002",
        authority_ref=prepared.authority.authority_id,
        prepared_context_ref="ctx-002",
        final_check_ref="check-002",
    )
    assert bundle["execution_attestation"]["decision"] == "BLOCK"
    assert bundle["execution_attestation"]["reason"] == "STALE_CONTEXT"
    assert bundle["execution_attestation"]["effect"] == "NONE"
    assert bundle["references"]["commit"] is None
