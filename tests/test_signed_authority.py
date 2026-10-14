import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ega.models import AuthorizationScope, DecisionRecord, EvidenceItem, ExecutionAuthority, RuntimeIntent
from ega.evidence import authorization_scope_digest, decision_record_digest, runtime_intent_digest
from ega.signed_authority import (
    AuthorityEnvelopeError,
    sign_authority,
    verify_signed_authority,
)


@pytest.fixture
def key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def authority():
    record = decision_record()
    return ExecutionAuthority(
        authority_id="auth-1",
        principal="robot-controller",
        action="set_joint_positions",
        target="so100-01",
        parameters={"shoulder_pan.pos": 1.0},
        environment="lab-1",
        source_decision="decision-7",
        decision_record_ref="decision-7",
        decision_record_digest=__import__("ega.evidence", fromlist=["decision_record_digest"]).decision_record_digest(record),
    )


def sign(authority, key, **overrides):
    args = dict(
        private_key=key,
        issuer="ega-prod",
        key_id="ega-key-1",
        issued_at=100,
        not_before=100,
        expires_at=200,
        jti="authority-jti-1",
    )
    args.update(overrides)
    return sign_authority(authority, **args)


def runtime_intent(intent_ref="intent-7", decision_ref="decision-7", **overrides):
    values = dict(
        principal="robot-controller",
        action="set_joint_positions",
        target="so100-01",
        parameters={"shoulder_pan.pos": 1.0},
        environment="lab-1",
        decision_ref=decision_ref,
        intent_ref=intent_ref,
    )
    values.update(overrides)
    return RuntimeIntent(**values)


def authorization_scope(scope_ref="scope-7", **overrides):
    values = dict(
        principal="robot-controller",
        action="set_joint_positions",
        target="so100-01",
        environment="lab-1",
        parameter_constraints={"shoulder_pan.pos": {"min": -3, "max": 3}},
        scope_ref=scope_ref,
    )
    values.update(overrides)
    return AuthorizationScope(**values)


def decision_record(record_id="decision-7", **overrides):
    intent = runtime_intent(decision_ref=record_id)
    scope = authorization_scope()
    values = dict(
        decision_id=record_id,
        decision_time="2026-10-14T08:00:00Z",
        intent_ref=intent.intent_ref,
        authorization_scope_ref=scope.scope_ref,
        intent_digest=runtime_intent_digest(intent),
        authorization_scope_digest=authorization_scope_digest(scope),
    )
    values.update(overrides)
    return DecisionRecord(**values)


def verify(artifact, key, **overrides):
    args = dict(
        trusted_keys={"ega-key-1": key.public_key()},
        expected_issuer="ega-prod",
        now=150,
        is_revoked=lambda _jti: False,
        decision_record_resolver=lambda record_id: decision_record(record_id),
        intent_resolver=lambda intent_ref: runtime_intent(intent_ref=intent_ref),
        scope_resolver=lambda scope_ref: authorization_scope(scope_ref=scope_ref),
    )
    args.update(overrides)
    return verify_signed_authority(artifact, **args)


def test_signed_authority_round_trip_binds_decision_lineage(authority, key):
    artifact = sign(authority, key)
    record = decision_record()
    verified = verify(artifact, key, decision_record_resolver=lambda record_id: record)
    assert verified["authority_id"] == "auth-1"
    assert verified["source_decision"] == "decision-7"
    assert verified["decision_record_ref"] == "decision-7"
    assert verified["decision_record_digest"] == __import__("ega.evidence", fromlist=["decision_record_digest"]).decision_record_digest(record)


def test_modified_authority_claims_fail_signature(authority, key):
    envelope = json.loads(sign(authority, key))
    envelope["claims"]["authority"]["target"] = "other-robot"
    with pytest.raises(AuthorityEnvelopeError, match="signature verification failed"):
        verify(json.dumps(envelope).encode(), key)


def test_untrusted_key_fails_closed(authority, key):
    artifact = sign(authority, key)
    other = Ed25519PrivateKey.generate()
    with pytest.raises(AuthorityEnvelopeError, match="signature verification failed"):
        verify(artifact, other)


def test_wrong_issuer_fails_closed(authority, key):
    with pytest.raises(AuthorityEnvelopeError, match="issuer is not trusted"):
        verify(sign(authority, key), key, expected_issuer="other-issuer")


def test_expired_authority_fails_closed(authority, key):
    with pytest.raises(AuthorityEnvelopeError, match="not currently valid"):
        verify(sign(authority, key), key, now=200)


def test_revoked_authority_fails_closed(authority, key):
    with pytest.raises(AuthorityEnvelopeError, match="has been revoked"):
        verify(sign(authority, key), key, is_revoked=lambda _jti: True)


def test_revocation_provider_failure_fails_closed(authority, key):
    def unavailable(_jti):
        raise RuntimeError("offline")
    with pytest.raises(AuthorityEnvelopeError, match="revocation check failed"):
        verify(sign(authority, key), key, is_revoked=unavailable)


@pytest.mark.parametrize("result", [None, 0, 1, "false"])
def test_non_boolean_revocation_result_fails_closed(authority, key, result):
    with pytest.raises(AuthorityEnvelopeError, match="non-boolean"):
        verify(sign(authority, key), key, is_revoked=lambda _jti: result)


def test_signing_requires_decision_record_lineage(key):
    authority = ExecutionAuthority(
        authority_id="auth-2",
        principal="robot-controller",
        action="move",
        target="so100-01",
        parameters={"x": 1.0},
        environment="lab-1",
        source_decision="decision-8",
    )
    with pytest.raises(AuthorityEnvelopeError, match="decision_record_ref"):
        sign(authority, key)


def test_tampered_signature_fails(authority, key):
    envelope = json.loads(sign(authority, key))
    envelope["signature"] = "AAAA"
    with pytest.raises(AuthorityEnvelopeError, match="signature verification failed"):
        verify(json.dumps(envelope).encode(), key)


def test_preferred_issuance_entry_point_evaluates_scope_and_binds_decision_record(key):
    from ega.models import AuthorizationScope, DecisionRecord, RuntimeIntent
    from ega.signed_authority import issue_signed_authority

    intent = RuntimeIntent(
        principal="robot-controller",
        action="move",
        target="so100-01",
        parameters={"x": 1.0},
        environment="lab-1",
        decision_ref="decision-9",
        intent_ref="intent-9",
    )
    scope = AuthorizationScope(
        principal="robot-controller",
        action="move",
        target="so100-01",
        environment="lab-1",
        parameter_constraints={"x": {"min": 0, "max": 2}},
        scope_ref="scope-9",
    )
    record = DecisionRecord(
        decision_id="decision-9",
        decision_time="2026-10-14T08:00:00Z",
        intent_ref="intent-9",
        authorization_scope_ref="scope-9",
        intent_digest=runtime_intent_digest(intent),
        authorization_scope_digest=authorization_scope_digest(scope),
    )
    artifact = issue_signed_authority(
        intent,
        scope,
        decision_record=record,
        private_key=key,
        issuer="ega-prod",
        key_id="ega-key-1",
        issued_at=100,
        not_before=100,
        expires_at=200,
        jti="authority-jti-9",
    )
    record = DecisionRecord(
        decision_id="decision-9",
        decision_time="2026-10-14T08:00:00Z",
        intent_ref="intent-9",
        authorization_scope_ref="scope-9",
        intent_digest=runtime_intent_digest(intent),
        authorization_scope_digest=authorization_scope_digest(scope),
    )
    claims = verify(
        artifact, key,
        decision_record_resolver=lambda record_id: record,
        intent_resolver=lambda _ref: intent,
        scope_resolver=lambda _ref: scope,
    )
    assert claims["parameters"] == {"x": 1.0}
    assert claims["decision_record_ref"] == "decision-9"
    assert claims["decision_record_digest"]


def test_preferred_issuance_entry_point_rejects_out_of_scope_intent(key):
    from ega.models import AuthorizationScope, DecisionRecord, RuntimeIntent
    from ega.signed_authority import issue_signed_authority

    intent = RuntimeIntent(
        principal="robot-controller",
        action="move",
        target="so100-01",
        parameters={"x": 99.0},
        environment="lab-1",
        decision_ref="decision-10",
        intent_ref="intent-10",
    )
    scope = AuthorizationScope(
        principal="robot-controller",
        action="move",
        target="so100-01",
        environment="lab-1",
        parameter_constraints={"x": {"min": 0, "max": 2}},
        scope_ref="scope-10",
    )
    record = DecisionRecord(
        decision_id="decision-10",
        decision_time="2026-10-14T08:00:00Z",
        intent_ref="intent-10",
        authorization_scope_ref="scope-10",
        intent_digest=runtime_intent_digest(intent),
        authorization_scope_digest=authorization_scope_digest(scope),
    )
    from ega.authority import AuthorizationError
    with pytest.raises(AuthorizationError, match="outside authorization scope"):
        issue_signed_authority(
            intent,
            scope,
            decision_record=record,
            private_key=key,
            issuer="ega-prod",
            key_id="ega-key-1",
            issued_at=100,
            not_before=100,
            expires_at=200,
            jti="authority-jti-10",
        )



def test_signed_authority_rejects_missing_decision_record(authority, key):
    with pytest.raises(AuthorityEnvelopeError, match="resolution failed"):
        verify(sign(authority, key), key, decision_record_resolver=lambda _ref: (_ for _ in ()).throw(KeyError("missing")))


def test_signed_authority_rejects_decision_record_digest_mismatch(authority, key):
    wrong_record = decision_record("decision-7", intent_ref="different-intent")
    with pytest.raises(AuthorityEnvelopeError, match="digest mismatch"):
        verify(sign(authority, key), key, decision_record_resolver=lambda _ref: wrong_record)


def test_signed_authority_rejects_decision_record_id_mismatch(authority, key):
    wrong_record = decision_record("another-decision")
    with pytest.raises(AuthorityEnvelopeError, match="ID does not match"):
        verify(sign(authority, key), key, decision_record_resolver=lambda _ref: wrong_record)


def test_signed_authority_requires_resolver(authority, key):
    with pytest.raises(AuthorityEnvelopeError, match="runtime-intent resolver is required"):
        verify_signed_authority(
            sign(authority, key),
            trusted_keys={"ega-key-1": key.public_key()},
            expected_issuer="ega-prod",
            now=150,
            is_revoked=lambda _jti: False,
            decision_record_resolver=lambda ref: decision_record(ref),
        )



def test_decision_record_digest_rejects_non_finite_evidence_values():
    from ega.evidence import decision_record_digest

    record = DecisionRecord(
        decision_id="decision-nan",
        decision_time="2026-10-14T08:00:00Z",
        intent_ref="intent-nan",
        authorization_scope_ref="scope-nan",
        evidence_items=(
            EvidenceItem(
                evidence_ref="sensor-1",
                digest="sha256:sample",
                observed_at="2026-10-14T08:00:00Z",
                evaluation_status="VALID",
                value=float("nan"),
            ),
        ),
    )
    with pytest.raises(ValueError):
        decision_record_digest(record)



def test_signed_authority_rejects_resolved_intent_digest_mismatch(authority, key):
    wrong_intent = runtime_intent(parameters={"shoulder_pan.pos": 2.0})
    with pytest.raises(AuthorityEnvelopeError, match="runtime-intent digest mismatch"):
        verify(sign(authority, key), key, intent_resolver=lambda _ref: wrong_intent)


def test_signed_authority_rejects_resolved_scope_digest_mismatch(authority, key):
    wrong_scope = authorization_scope(parameter_constraints={"shoulder_pan.pos": {"min": -1, "max": 1}})
    with pytest.raises(AuthorityEnvelopeError, match="authorization-scope digest mismatch"):
        verify(sign(authority, key), key, scope_resolver=lambda _ref: wrong_scope)


def test_signed_authority_rejects_aee_condition_without_evidence(authority, key):
    from ega.models import AEECondition

    record = decision_record(aee_conditions=(AEECondition("c1", "missing-evidence"),))
    artifact = sign_authority(
        {**authority.__dict__, "decision_record_digest": decision_record_digest(record)},
        private_key=key, issuer="ega-prod", key_id="ega-key-1",
        issued_at=100, not_before=100, expires_at=200, jti="bad-evidence-link",
    )
    with pytest.raises(AuthorityEnvelopeError, match="AEE condition references evidence absent"):
        verify(artifact, key, decision_record_resolver=lambda _ref: record)
