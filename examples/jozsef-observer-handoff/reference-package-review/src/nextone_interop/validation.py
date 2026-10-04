"""Schema loading and envelope validation (fail-closed)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from .clock import parse_rfc3339_utc

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "evidence-envelope-v1.schema.json"

# Active format enforcement (timestamp-validation refinement): the schema declares
# "format": "date-time" for observed_at, and this checker makes the keyword
# binding. The check reuses the strict, range-validating RFC 3339 UTC parser,
# so impossible calendar/time values (month 13, February 30, hour 25, ...)
# are rejected at schema validation, before integrity verification.
FORMAT_CHECKER = jsonschema.FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=())
def _check_date_time(value: Any) -> bool:
    if not isinstance(value, str):
        return True  # the "type" keyword rejects non-strings; nothing to check here
    try:
        parse_rfc3339_utc(value)
    except ValueError:
        return False
    return True


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def get_validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema(), format_checker=FORMAT_CHECKER)


def validate_envelope(envelope: Any) -> None:
    """Validate an object against EvidenceEnvelope v1; raise on violation."""
    get_validator().validate(envelope)


def is_valid_envelope(envelope: Any) -> bool:
    try:
        validate_envelope(envelope)
    except jsonschema.ValidationError:
        return False
    return True
