"""Correction 2: evidence_id is a strong observation identity.

``evidence_id = "ev1:" + SHA-256(nextone-canonical-json-v1(identity payload))``
over subject, target, observed state, observed value, observed time, and
provenance identity. It is derived independently of ``integrity.digest``
(different input, different purpose) and includes no EGA authorization state.
"""

from __future__ import annotations

import re

import pytest

from conftest import ENVELOPE_RELPATHS, load_fixture
from nextone_interop.evidence import derive_evidence_id
from nextone_interop.fixturegen import CATALOG_PATH, FixtureSpec, build_envelope

EVIDENCE_ID_RE = re.compile(r"^ev1:[0-9a-f]{64}$")

_BASE_PROVENANCE = {
    "source_id": "local-catalog",
    "source_kind": "local_catalog",
    "collection_method": "read_only",
    "source_locator": "catalog/T1/SKU1/price_cents",
}

_BASE_IDENTITY = {
    "subject": {"type": "tenant", "id": "T1"},
    "target": {"resource": "catalog", "entity_id": "SKU1", "field": "price_cents"},
    "observed_state": "KNOWN",
    "observed_value": 2500,
    "observed_at": "2026-10-03T19:00:00Z",
    "provenance": _BASE_PROVENANCE,
}


def test_evidence_id_format_on_all_fixtures():
    for relpath in ENVELOPE_RELPATHS:
        envelope = load_fixture(relpath)
        assert EVIDENCE_ID_RE.match(envelope["evidence_id"]), relpath


def test_all_fixtures_have_unique_evidence_ids():
    ids = [load_fixture(relpath)["evidence_id"] for relpath in ENVELOPE_RELPATHS]
    assert len(set(ids)) == len(ids), "every observation must have its own identity"


def test_same_identity_produces_same_id():
    first = derive_evidence_id(**_BASE_IDENTITY)
    second = derive_evidence_id(**_BASE_IDENTITY)
    assert first == second
    assert EVIDENCE_ID_RE.match(first)


def _variant(**changes):
    identity = dict(_BASE_IDENTITY)
    identity.update(changes)
    return identity


_IDENTITY_VARIANTS = {
    "subject": _variant(subject={"type": "tenant", "id": "T2"}),
    "target": _variant(target={"resource": "catalog", "entity_id": "SKU2", "field": "price_cents"}),
    "observed_state": _variant(observed_state="UNKNOWN", observed_value=None),
    "observed_value": _variant(observed_value=2600),
    "observed_at": _variant(observed_at="2026-10-03T19:00:01Z"),
    "provenance.source_id": _variant(
        provenance={**_BASE_PROVENANCE, "source_id": "local-catalog-alt"}
    ),
}


@pytest.mark.parametrize(
    "identity", list(_IDENTITY_VARIANTS.values()), ids=list(_IDENTITY_VARIANTS)
)
def test_changing_any_identity_field_changes_id(identity):
    assert derive_evidence_id(**identity) != derive_evidence_id(**_BASE_IDENTITY)


def test_evidence_id_is_not_the_integrity_digest():
    golden = load_fixture("golden/known_price_2500.json")
    raw_digest = golden["integrity"]["digest"].removeprefix("sha256:")
    assert golden["evidence_id"] != golden["integrity"]["digest"]
    assert golden["evidence_id"] != "ev1:" + raw_digest


def test_same_timestamp_conflicting_observations_have_distinct_ids():
    spec_current = FixtureSpec("conflict/observation_a.json", "current", "2026-10-02T08:00:00Z")
    spec_prior = FixtureSpec("conflict/observation_b.json", "prior", "2026-10-02T08:00:00Z")
    observation_a = build_envelope(CATALOG_PATH, spec_current)
    observation_b = build_envelope(CATALOG_PATH, spec_prior)
    assert observation_a["observed_at"] == observation_b["observed_at"]
    assert observation_a["observed_value"] != observation_b["observed_value"]
    assert observation_a["evidence_id"] != observation_b["evidence_id"]
    assert observation_a["integrity"]["digest"] != observation_b["integrity"]["digest"]


def test_on_disk_conflict_fixtures_retain_independent_ids_and_digests():
    observation_a = load_fixture("conflict/observation_a.json")
    observation_b = load_fixture("conflict/observation_b.json")
    assert observation_a["evidence_id"] != observation_b["evidence_id"]
    assert observation_a["integrity"]["digest"] != observation_b["integrity"]["digest"]
    assert observation_a["provenance"]["source_id"] != observation_b["provenance"]["source_id"]
