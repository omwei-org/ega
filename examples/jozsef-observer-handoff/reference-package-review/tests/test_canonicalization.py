"""AT-05 .. AT-07: canonicalization determinism, digest sensitivity, no self-reference."""

from __future__ import annotations

import copy

from conftest import ENVELOPE_RELPATHS
from nextone_interop.canonical import (
    build_integrity,
    canonicalize,
    digest_payload,
    verify_integrity,
)


def test_at_05_key_ordering_does_not_change_digest(golden):
    reordered = dict(reversed(list(golden.items())))
    nested = copy.deepcopy(reordered)
    nested["provenance"] = dict(reversed(list(nested["provenance"].items())))
    nested["subject"] = dict(reversed(list(nested["subject"].items())))
    assert canonicalize({k: v for k, v in golden.items() if k != "integrity"}) == canonicalize(
        {k: v for k, v in nested.items() if k != "integrity"}
    )
    assert digest_payload(golden) == digest_payload(nested)


def test_at_06_changing_covered_fields_changes_digest(golden):
    base = digest_payload(golden)

    changed = copy.deepcopy(golden)
    changed["observed_value"] = 2600
    assert digest_payload(changed) != base

    changed = copy.deepcopy(golden)
    changed["observed_at"] = "2026-10-03T19:00:01Z"
    assert digest_payload(changed) != base

    changed = copy.deepcopy(golden)
    changed["provenance"]["source_id"] = "another-source"
    assert digest_payload(changed) != base

    changed = copy.deepcopy(golden)
    changed["provenance"]["source_locator"] = "catalog/T1/SKU1/other_field"
    assert digest_payload(changed) != base

    changed = copy.deepcopy(golden)
    changed["subject"]["id"] = "T2"
    assert digest_payload(changed) != base

    changed = copy.deepcopy(golden)
    changed["temporal_basis"]["timestamp_semantics"] = "request_received_at"
    assert digest_payload(changed) != base


def test_at_07_integrity_field_not_hashed(golden):
    recomputed = digest_payload(golden)
    assert recomputed == golden["integrity"]["digest"]

    tampered = copy.deepcopy(golden)
    tampered["integrity"]["digest"] = "sha256:" + "0" * 64
    assert digest_payload(tampered) == recomputed, "digest input must exclude the integrity object"
    assert verify_integrity(tampered) is False


def test_all_fixture_digests_verify(envelopes):
    for relpath in ENVELOPE_RELPATHS:
        assert verify_integrity(envelopes[relpath]), f"{relpath}: digest does not verify"


def test_integrity_object_form(golden):
    integrity = golden["integrity"]
    assert integrity["canonicalization"] == "nextone-canonical-json-v1"
    assert integrity["algorithm"] == "sha256"
    assert integrity["digest"].startswith("sha256:")


def test_build_integrity_matches_digest_payload(golden):
    payload = copy.deepcopy(golden)
    del payload["integrity"]
    assert build_integrity(payload) == golden["integrity"]
