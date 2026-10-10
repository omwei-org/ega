import pytest
import requests

from ega.comos_adapter import EGAAuthorizationDenied, EGAHTTPGate


class FakeResponse:
    def __init__(self, body=None, error=None):
        self.body, self.error = body, error
    def raise_for_status(self):
        if self.error:
            raise self.error
    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []
    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        if self.error:
            raise self.error
        return self.response


def valid_body():
    return {"decision": "COMMIT", "reason": "AUTHORITY_VALID",
            "applied": True, "effect": "NOT_EXECUTED"}


def test_explicit_commit_returns_permit_and_binds_request_payload():
    session = FakeSession(FakeResponse(valid_body()))
    gate = EGAHTTPGate("http://127.0.0.1:8000/", session=session)
    authority = {"authority_id": "auth-1"}
    intent = {"action": "order_create",
              "parameters": {"items": [{"product_id": "p1", "quantity": 1}]}}
    permit = gate.authorize_before_effect(authority=authority, intent=intent, context_epoch=17)
    assert permit.decision == "COMMIT"
    url, payload, timeout = session.calls[0]
    assert url == "http://127.0.0.1:8000/v1/evaluate"
    assert payload["authority"] == authority
    assert payload["intent"] == intent
    assert payload["context_epoch"] == 17
    assert timeout == 3.0


@pytest.mark.parametrize("body", [
    {"decision": "BLOCK", "reason": "SCOPE_MISMATCH", "applied": False, "effect": "NOT_EXECUTED"},
    {"decision": "COMMIT", "reason": "ok", "applied": False, "effect": "NOT_EXECUTED"},
    {"decision": "COMMIT", "reason": "ok", "applied": True, "effect": "EXECUTED"},
    {"decision": "COMMIT", "reason": "ok", "applied": True},
    None, [],
])
def test_any_ambiguous_or_non_commit_response_denies(body):
    gate = EGAHTTPGate(session=FakeSession(FakeResponse(body)))
    with pytest.raises(EGAAuthorizationDenied):
        gate.authorize_before_effect(authority={}, intent={}, context_epoch=1)


@pytest.mark.parametrize("error", [
    requests.Timeout("timeout"), requests.ConnectionError("offline"),
])
def test_transport_failure_denies(error):
    gate = EGAHTTPGate(session=FakeSession(error=error))
    with pytest.raises(EGAAuthorizationDenied):
        gate.authorize_before_effect(authority={}, intent={}, context_epoch=1)


def test_http_error_denies():
    gate = EGAHTTPGate(session=FakeSession(FakeResponse(error=requests.HTTPError("503"))))
    with pytest.raises(EGAAuthorizationDenied):
        gate.authorize_before_effect(authority={}, intent={}, context_epoch=1)


def test_effect_callback_is_not_invoked_on_block():
    called = []
    body = {"decision": "BLOCK", "reason": "denied", "applied": False, "effect": "NOT_EXECUTED"}
    gate = EGAHTTPGate(session=FakeSession(FakeResponse(body)))
    with pytest.raises(EGAAuthorizationDenied):
        gate.run_if_authorized(lambda: called.append("effect"), authority={}, intent={}, context_epoch=1)
    assert called == []


def test_effect_callback_runs_only_after_valid_commit():
    called = []
    gate = EGAHTTPGate(session=FakeSession(FakeResponse(valid_body())))
    result, permit = gate.run_if_authorized(
        lambda: called.append("effect") or "done", authority={}, intent={}, context_epoch=1)
    assert result == "done"
    assert called == ["effect"]
    assert permit.decision == "COMMIT"
