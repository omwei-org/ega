"""AT-01 .. AT-04: schema validity and KNOWN/UNKNOWN contracts."""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest

from conftest import ENVELOPE_RELPATHS
from nextone_interop import SCHEMA_VERSION
from nextone_interop.evidence import forbidden_semantics_present
from nextone_interop.validation import get_validator, load_schema, validate_envelope

FORBIDDEN_TEXT_TOKENS = (
    "authorized_price",
    "expected_price",
    "predicate_result",
    "FRESH",
    "STALE",
    "ALLOW",
    "DENY",
    "HOLD",
    "ESCALATE",
    "REFUSE",
    "AEE",
    "authorization",
    "execution_authority",
    "commit_condition",
)


def test_schema_is_draft_2020_12_with_stable_id():
    schema = load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].startswith("https://nextone.local/schemas/")
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION


def test_at_01_golden_schema_validity(golden):
    validate_envelope(golden)  # raises on violation


def test_at_02_golden_semantics_present(golden):
    assert golden["subject"] == {"type": "tenant", "id": "T1"}
    assert golden["target"] == {"resource": "catalog", "entity_id": "SKU1", "field": "price_cents"}
    assert golden["observed_state"] == "KNOWN"
    assert golden["observed_value"] == 2500
    for field in (
        "observed_at",
        "temporal_basis",
        "provenance",
        "uncertainty",
        "integrity",
        "schema_version",
        "evidence_id",
    ):
        assert field in golden


def test_at_02_golden_semantics_absent(golden):
    assert forbidden_semantics_present(golden) == []
    for token in FORBIDDEN_TEXT_TOKENS:
        assert token not in json.dumps(golden, ensure_ascii=False), (
            f"forbidden token in golden evidence: {token}"
        )


def test_all_envelope_fixtures_validate(envelopes):
    for relpath in ENVELOPE_RELPATHS:
        validate_envelope(envelopes[relpath])  # raises on violation


def test_at_03_unknown_requires_null_value(envelopes):
    unknown = envelopes["negative/unknown_price.json"]
    validate_envelope(unknown)
    malformed = copy.deepcopy(unknown)
    malformed["observed_value"] = 2500
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(malformed)


def test_at_04_known_requires_non_null_value(envelopes):
    known = envelopes["golden/known_price_2500.json"]
    malformed = copy.deepcopy(known)
    malformed["observed_value"] = None
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(malformed)


def test_known_with_missing_value_fails(golden):
    malformed = copy.deepcopy(golden)
    del malformed["observed_value"]
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(malformed)


def test_additional_properties_rejected(golden):
    malformed = copy.deepcopy(golden)
    malformed["note"] = "extra"
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(malformed)


def test_observed_at_must_be_utc_z(golden):
    malformed = copy.deepcopy(golden)
    malformed["observed_at"] = "2026-10-03T19:00:00+02:00"
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(malformed)


def test_validator_is_draft_2020_12():
    validator = get_validator()
    assert isinstance(validator, jsonschema.Draft202012Validator)
