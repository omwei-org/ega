from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "fixtures"
EGA_CONTEXT_DIR = ROOT / "tests" / "ega_context"

ENVELOPE_RELPATHS = (
    "golden/known_price_2500.json",
    "negative/older_observation_price_2500.json",
    "negative/known_price_2600.json",
    "negative/unknown_price.json",
    "conflict/observation_a.json",
    "conflict/observation_b.json",
)


def load_fixture(relpath: str) -> dict:
    return json.loads((FIXTURES_DIR / relpath).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def golden() -> dict:
    return load_fixture("golden/known_price_2500.json")


@pytest.fixture(scope="session")
def envelopes() -> dict[str, dict]:
    return {relpath: load_fixture(relpath) for relpath in ENVELOPE_RELPATHS}


@pytest.fixture(scope="session")
def ega_authorization_context() -> dict:
    return json.loads((EGA_CONTEXT_DIR / "authorized_price_2500.json").read_text(encoding="utf-8"))
