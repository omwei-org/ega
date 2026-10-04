"""AT-11, AT-12, AT-14, AT-15: Observer is evidence-only, read-only, source-read, deterministic."""

from __future__ import annotations

import hashlib
import inspect
import json

import nextone_interop.observer as observer_module
from conftest import ROOT
from nextone_interop.canonical import verify_integrity
from nextone_interop.catalog_source import LocalJsonCatalogSource
from nextone_interop.clock import FixedUtcClock, parse_rfc3339_utc
from nextone_interop.evidence import derive_evidence_id, forbidden_semantics_present
from nextone_interop.fixturegen import CATALOG_PATH, GOLDEN_SPEC, build_envelope, render_envelope
from nextone_interop.observer import Observer
from nextone_interop.validation import validate_envelope

FORBIDDEN_API_NAMES = {
    "authorize",
    "approve",
    "allow",
    "deny",
    "execute",
    "commit",
    "grant",
    "resolve_policy",
    "evaluate_policy",
}

EXECUTION_TERMS = ("retail_sale", "createBrokeredPendingOrder", "order")

FIXED_TIME = "2026-10-03T19:00:00Z"


def make_observer(snapshot: str = "current", observed_at: str = FIXED_TIME) -> Observer:
    """Observer with a frozen clock: deterministic time without touching the normal API."""
    source = LocalJsonCatalogSource(CATALOG_PATH, snapshot=snapshot)
    return Observer(source, clock=FixedUtcClock(parse_rfc3339_utc(observed_at)))


def observe_price(observer: Observer) -> dict:
    return observer.observe(
        subject_type="tenant",
        tenant_id="T1",
        resource="catalog",
        entity_id="SKU1",
        field="price_cents",
    )


def test_at_11_observer_cannot_authorize():
    public_api = {
        name
        for name, member in inspect.getmembers(Observer)
        if not name.startswith("_") and callable(member)
    }
    assert public_api == {"observe"}, f"unexpected Observer API surface: {public_api}"
    assert FORBIDDEN_API_NAMES.isdisjoint(public_api)
    module_functions = {
        name
        for name, member in inspect.getmembers(observer_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert FORBIDDEN_API_NAMES.isdisjoint(module_functions)


def test_at_12_observer_cannot_execute():
    source = inspect.getsource(observer_module)
    for term in EXECUTION_TERMS:
        assert term not in source, f"execution term leaked into Observer: {term}"


def test_observer_output_is_valid_evidence_only_envelope():
    envelope = observe_price(make_observer())
    validate_envelope(envelope)
    assert forbidden_semantics_present(envelope) == []
    assert verify_integrity(envelope)


def test_at_14_value_is_read_through_source_interface(tmp_path):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "source_id": "local-catalog",
                "locator_prefix": "catalog",
                "snapshots": {"current": {"data": {"T1": {"SKU1": {"price_cents": 2600}}}}},
            }
        ),
        encoding="utf-8",
    )
    observer = Observer(
        LocalJsonCatalogSource(catalog, "current"),
        clock=FixedUtcClock(parse_rfc3339_utc(FIXED_TIME)),
    )
    envelope = observe_price(observer)
    assert envelope["observed_value"] == 2600, "value must come from the source, not from constants"
    assert envelope["observed_state"] == "KNOWN"


def test_at_14_source_is_queried_for_the_observed_target():
    calls: list[tuple[str, str, str]] = []

    class SpySource:
        def read_field(self, tenant_id: str, sku: str, field: str):
            calls.append((tenant_id, sku, field))
            return 2500

        def describe(self):
            from nextone_interop.catalog_source import SourceDescriptor

            return SourceDescriptor("local-catalog", "local_catalog", "catalog")

    envelope = Observer(
        SpySource(),
        clock=FixedUtcClock(parse_rfc3339_utc(FIXED_TIME)),
    ).observe(
        subject_type="tenant",
        tenant_id="T1",
        resource="catalog",
        entity_id="SKU1",
        field="price_cents",
    )
    assert calls == [("T1", "SKU1", "price_cents")]
    assert envelope["observed_value"] == 2500


def test_at_15_repeatability_same_inputs_same_bytes():
    first = render_envelope(build_envelope(CATALOG_PATH, GOLDEN_SPEC))
    second = render_envelope(build_envelope(CATALOG_PATH, GOLDEN_SPEC))
    assert first == second
    on_disk = (ROOT / "fixtures" / "golden" / "known_price_2500.json").read_text(encoding="utf-8")
    assert first == on_disk


def test_at_15_different_time_changes_evidence_id_and_digest():
    a = observe_price(make_observer(observed_at="2026-10-03T19:00:00Z"))
    b = observe_price(make_observer(observed_at="2026-10-03T19:00:01Z"))
    assert a["evidence_id"] != b["evidence_id"]
    assert a["integrity"]["digest"] != b["integrity"]["digest"]


def test_temporal_basis_is_evidence_only():
    envelope = observe_price(make_observer())
    assert envelope["temporal_basis"] == {
        "type": "point_in_time",
        "timestamp_semantics": "observation_completed_at",
        "clock": "UTC",
    }


def test_uncertainty_is_not_invented():
    envelope = observe_price(make_observer())
    assert envelope["uncertainty"] == {
        "source_confidence": None,
        "confidence_semantics": "not_supplied",
    }


def test_unknown_observation_when_source_has_no_value():
    envelope = observe_price(make_observer(snapshot="empty"))
    assert envelope["observed_state"] == "UNKNOWN"
    assert envelope["observed_value"] is None
    assert envelope["provenance"]["collection_method"] == "read_only"


def test_evidence_id_is_deterministic(golden):
    derived = derive_evidence_id(
        subject=golden["subject"],
        target=golden["target"],
        observed_state=golden["observed_state"],
        observed_value=golden["observed_value"],
        observed_at=golden["observed_at"],
        provenance=golden["provenance"],
    )
    assert derived == golden["evidence_id"]


def test_observation_does_not_mutate_catalog():
    before = hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    observe_price(make_observer())
    observe_price(make_observer(snapshot="empty"))
    after = hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    assert before == after, "Observer collection must not mutate the observed system (INV-02)"
