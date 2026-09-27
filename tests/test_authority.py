from ega.authority import issue_authority
from ega.models import RuntimeIntent

def test_issue_authority():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": "20%"},
        environment="plant-7",
        decision_ref="raig-decision-784",
    )
    authority = issue_authority(intent)

    assert authority.status == "VALID"
    assert authority.principal == "agent-123"
    assert authority.target == "valve-v1"
    assert authority.parameters["value"] == "20%"
    assert authority.source_decision == "raig-decision-784"

def test_authority_does_not_execute():
    intent = RuntimeIntent(
        principal="agent-123",
        action="open",
        target="valve-v1",
        parameters={"value": "20%"},
        environment="plant-7",
        decision_ref="raig-decision-784",
    )
    authority = issue_authority(intent)
    assert authority.status == "VALID"
    assert not hasattr(authority, "execute")
    assert not hasattr(authority, "commit")
