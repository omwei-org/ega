import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ega.models import ExecutionAuthority
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
    return ExecutionAuthority(
        authority_id="auth-1",
        principal="robot-controller",
        action="set_joint_positions",
        target="so100-01",
        parameters={"shoulder_pan.pos": 1.0},
        environment="lab-1",
        source_decision="decision-7",
        decision_record_ref="decision-7",
        decision_record_digest="sha256:decision-digest",
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


def verify(artifact, key, **overrides):
    args = dict(
        trusted_keys={"ega-key-1": key.public_key()},
        expected_issuer="ega-prod",
        now=150,
        is_revoked=lambda _jti: False,
    )
    args.update(overrides)
    return verify_signed_authority(artifact, **args)


def test_signed_authority_round_trip_binds_decision_lineage(authority, key):
    artifact = sign(authority, key)
    verified = verify(artifact, key)
    assert verified["authority_id"] == "auth-1"
    assert verified["source_decision"] == "decision-7"
    assert verified["decision_record_ref"] == "decision-7"
    assert verified["decision_record_digest"] == "sha256:decision-digest"


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
    )
    scope = AuthorizationScope(
        principal="robot-controller",
        action="move",
        target="so100-01",
        environment="lab-1",
        parameter_constraints={"x": {"min": 0, "max": 2}},
    )
    record = DecisionRecord(
        decision_id="decision-9",
        decision_time="2026-10-14T08:00:00Z",
        intent_ref="intent-9",
        authorization_scope_ref="scope-9",
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
    claims = verify(artifact, key)
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
    )
    scope = AuthorizationScope(
        principal="robot-controller",
        action="move",
        target="so100-01",
        environment="lab-1",
        parameter_constraints={"x": {"min": 0, "max": 2}},
    )
    record = DecisionRecord(
        decision_id="decision-10",
        decision_time="2026-10-14T08:00:00Z",
        intent_ref="intent-10",
        authorization_scope_ref="scope-10",
    )
    with pytest.raises(Exception, match="outside authorization scope"):
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
