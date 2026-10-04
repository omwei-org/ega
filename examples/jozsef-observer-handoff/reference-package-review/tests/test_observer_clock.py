"""Correction 3: the Observer owns observed_at via an injectable clock.

Normal ``observe()`` captures time from the Observer's clock and has no
timestamp parameter, so callers cannot inject arbitrary observation times.
Deterministic fixture/historical construction is a clearly separated path: it
injects a ``FixedUtcClock`` and flows through the same ``observe()`` method.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from conftest import ROOT
from nextone_interop.catalog_source import LocalJsonCatalogSource
from nextone_interop.clock import (
    FixedUtcClock,
    SystemUtcClock,
    format_rfc3339_utc,
    parse_rfc3339_utc,
)
from nextone_interop.fixturegen import (
    CATALOG_PATH,
    FIXTURE_SPECS,
    GOLDEN_SPEC,
    build_envelope,
    render_envelope,
)
from nextone_interop.observer import Observer

CATALOG = ROOT / "fixtures" / "catalog" / "catalog.json"
FIXED_TIME = "2026-10-03T19:00:00Z"
OBSERVE_KWARGS = {
    "subject_type": "tenant",
    "tenant_id": "T1",
    "resource": "catalog",
    "entity_id": "SKU1",
    "field": "price_cents",
}


def make_observer(clock=None, snapshot: str = "current") -> Observer:
    source = LocalJsonCatalogSource(CATALOG, snapshot=snapshot)
    return Observer(source, clock=clock)


def test_time_is_captured_from_the_injected_clock():
    observer = make_observer(clock=FixedUtcClock(parse_rfc3339_utc(FIXED_TIME)))
    envelope = observer.observe(**OBSERVE_KWARGS)
    assert envelope["observed_at"] == FIXED_TIME


def test_default_clock_reads_system_utc():
    assert isinstance(SystemUtcClock().now_utc().tzinfo, timezone)
    observer = make_observer()
    before = datetime.now(timezone.utc)
    envelope = observer.observe(**OBSERVE_KWARGS)
    after = datetime.now(timezone.utc)
    observed = parse_rfc3339_utc(envelope["observed_at"])
    assert observed.tzinfo is not None
    assert before <= observed <= after


def test_fixed_clock_is_deterministic():
    clock = FixedUtcClock(parse_rfc3339_utc(FIXED_TIME))
    first = make_observer(clock=clock).observe(**OBSERVE_KWARGS)
    second = make_observer(clock=clock).observe(**OBSERVE_KWARGS)
    assert first == second
    assert first["observed_at"] == FIXED_TIME


def test_observe_signature_has_no_timestamp_parameter():
    signature = inspect.signature(Observer.observe)
    assert "observed_at" not in signature.parameters
    assert set(signature.parameters) == {"self", "subject_type", "tenant_id", "resource", "entity_id", "field"}


def test_caller_cannot_inject_an_arbitrary_timestamp():
    observer = make_observer(clock=FixedUtcClock(parse_rfc3339_utc(FIXED_TIME)))
    with pytest.raises(TypeError):
        observer.observe(**OBSERVE_KWARGS, observed_at="2019-01-01T00:00:00Z")
    envelope = observer.observe(**OBSERVE_KWARGS)
    assert envelope["observed_at"] == FIXED_TIME


def test_naive_datetime_is_rejected_by_fixed_clock():
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedUtcClock(datetime(2026, 10, 3, 19, 0, 0))


def test_offset_datetime_is_normalized_to_utc():
    offset_clock = FixedUtcClock(
        datetime(2026, 10, 3, 21, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    )
    envelope = make_observer(clock=offset_clock).observe(**OBSERVE_KWARGS)
    assert envelope["observed_at"] == FIXED_TIME


def test_microseconds_are_rendered_with_six_digits():
    clock = FixedUtcClock(datetime(2026, 10, 3, 19, 0, 0, 123456, tzinfo=timezone.utc))
    envelope = make_observer(clock=clock).observe(**OBSERVE_KWARGS)
    assert envelope["observed_at"] == "2026-10-03T19:00:00.123456Z"


def test_format_rfc3339_rejects_naive_datetimes():
    with pytest.raises(ValueError, match="naive"):
        format_rfc3339_utc(datetime(2026, 10, 3, 19, 0, 0))


def test_parse_rfc3339_is_strict():
    assert parse_rfc3339_utc(FIXED_TIME) == datetime(2026, 10, 3, 19, 0, 0, tzinfo=timezone.utc)
    for bad in ("yesterday-ish", "2026-10-03 19:00:00", "2026-10-03T21:00:00+02:00", 2500):
        with pytest.raises(ValueError):
            parse_rfc3339_utc(bad)


def test_fixture_generation_remains_deterministic():
    first = render_envelope(build_envelope(CATALOG_PATH, GOLDEN_SPEC))
    second = render_envelope(build_envelope(CATALOG_PATH, GOLDEN_SPEC))
    assert first == second


def test_older_observation_fixture_is_intentionally_generatable():
    older_spec = FIXTURE_SPECS[1]
    envelope = build_envelope(CATALOG_PATH, older_spec)
    assert envelope["observed_at"] == older_spec.observed_at == "2026-10-01T09:00:00Z"
    assert envelope["observed_state"] == "KNOWN"
    assert envelope["observed_value"] == 2500
    serialized = render_envelope(envelope)
    assert "FRESH" not in serialized and "STALE" not in serialized
