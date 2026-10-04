"""AT-08, AT-09, AT-10: negative fixtures stay evidence-only; conflicts stay independent."""

from __future__ import annotations

import inspect

from nextone_interop.ega_seam import EgaSeamAdapter
from nextone_interop.evidence import forbidden_semantics_present

SEAM_API_FORBIDDEN = {"resolve", "merge", "arbitrate", "reconcile", "collapse"}


def test_at_08_older_observation_has_no_stale_verdict(envelopes):
    older = envelopes["negative/older_observation_price_2500.json"]
    golden = envelopes["golden/known_price_2500.json"]
    assert older["observed_value"] == 2500 == golden["observed_value"]
    assert older["observed_at"] < golden["observed_at"]
    assert forbidden_semantics_present(older) == []
    for token in ("FRESH", "STALE"):
        assert token not in str(older)


def test_at_09_value_mismatch_remains_evidence_only(envelopes):
    mismatch = envelopes["negative/known_price_2600.json"]
    assert mismatch["observed_state"] == "KNOWN"
    assert mismatch["observed_value"] == 2600
    assert mismatch["target"] == {"resource": "catalog", "entity_id": "SKU1", "field": "price_cents"}
    assert forbidden_semantics_present(mismatch) == []
    for token in ("predicate_result", "authorized_price", "expected_price", "DENY"):
        assert token not in str(mismatch)


def test_unknown_fixture_stays_unknown(envelopes):
    unknown = envelopes["negative/unknown_price.json"]
    assert unknown["observed_state"] == "UNKNOWN"
    assert unknown["observed_value"] is None
    assert unknown["observed_at"]
    assert unknown["provenance"]["collection_method"] == "read_only"


def test_at_10_conflicts_remain_separate(envelopes):
    a = envelopes["conflict/observation_a.json"]
    b = envelopes["conflict/observation_b.json"]
    assert a["target"] == b["target"]
    assert a["observed_value"] == 2500
    assert b["observed_value"] == 2600
    assert a["evidence_id"] != b["evidence_id"]
    assert a["integrity"]["digest"] != b["integrity"]["digest"]
    assert a["provenance"] != b["provenance"], "conflicting observations need independent provenance"

    seam = EgaSeamAdapter()
    presented = seam.present_all([a, b])
    assert len(presented) == 2, "seam must not merge conflicting observations"
    assert presented[0] == a and presented[1] == b
    assert presented[0] is not a, "seam must hand over a copy, not shared mutable state"


def test_seam_has_no_conflict_resolution_api():
    api = {
        name
        for name, member in inspect.getmembers(EgaSeamAdapter)
        if not name.startswith("_") and callable(member)
    }
    assert SEAM_API_FORBIDDEN.isdisjoint(api), f"seam exposes resolution semantics: {api}"
