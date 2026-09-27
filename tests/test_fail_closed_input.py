import pytest

from ega.authority import issue_authority
from ega.models import AuthorizationScope, RuntimeIntent


@pytest.mark.parametrize(
    "field",
    ["principal", "action", "target", "environment", "decision_ref"],
)
def test_required_authority_input(field):
    values = {
        "principal": "agent-123",
        "action": "open",
        "target": "valve-v1",
        "parameters": {"value": 20},
        "environment": "plant-7",
        "decision_ref": "raig-decision-784",
    }
    values[field] = ""

    intent = RuntimeIntent(**values)
    scope = AuthorizationScope(
        principal="agent-123",
        action="open",
        target="valve-v1",
        environment="plant-7",
        parameter_constraints={"value": {"min": 0, "max": 20}},
    )

    with pytest.raises(ValueError):
        issue_authority(intent, scope)
