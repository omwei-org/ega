import pytest
from ega.authority import issue_authority
from ega.models import RuntimeIntent

@pytest.mark.parametrize(
    "field",
    ["principal", "action", "target", "environment", "decision_ref"],
)
def test_required_authority_input(field):
    values = {
        "principal": "agent-123",
        "action": "open",
        "target": "valve-v1",
        "parameters": {"value": "20%"},
        "environment": "plant-7",
        "decision_ref": "raig-decision-784",
    }
    values[field] = ""
    with pytest.raises(ValueError):
        issue_authority(RuntimeIntent(**values))
