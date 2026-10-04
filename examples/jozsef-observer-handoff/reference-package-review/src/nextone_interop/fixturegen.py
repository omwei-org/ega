"""Deterministic fixture generation specification.

Every EvidenceEnvelope fixture is produced by the Observer reading through
the catalog source interface — no observed value is hard-coded here (AT-14).
Observation timestamps are fixed through ``FixedUtcClock`` injection, which
keeps generation deterministic (AT-15) while the normal Observer API
continues to capture time itself (validation refinement, Correction 3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog_source import LocalJsonCatalogSource
from .clock import FixedUtcClock, parse_rfc3339_utc
from .observer import Observer

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = PROJECT_ROOT / "fixtures" / "catalog" / "catalog.json"
FIXTURES_DIR = PROJECT_ROOT / "fixtures"


@dataclass(frozen=True)
class FixtureSpec:
    relative_path: str
    snapshot: str
    observed_at: str


_SUBJECT_TYPE = "tenant"
_TENANT = "T1"
_RESOURCE = "catalog"
_SKU = "SKU1"
_FIELD = "price_cents"

FIXTURE_SPECS: tuple[FixtureSpec, ...] = (
    FixtureSpec("golden/known_price_2500.json", "current", "2026-10-03T19:00:00Z"),
    FixtureSpec("negative/older_observation_price_2500.json", "current", "2026-10-01T09:00:00Z"),
    FixtureSpec("negative/known_price_2600.json", "prior", "2026-10-03T18:30:00Z"),
    FixtureSpec("negative/unknown_price.json", "empty", "2026-10-03T19:10:00Z"),
    FixtureSpec("conflict/observation_a.json", "current", "2026-10-02T08:00:00Z"),
    FixtureSpec("conflict/observation_b.json", "prior", "2026-10-02T08:05:00Z"),
)

GOLDEN_SPEC = FIXTURE_SPECS[0]


def build_envelope(
    catalog_path: str | Path,
    spec: FixtureSpec,
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Generate one EvidenceEnvelope by observing the catalog source.

    This is the deterministic fixture/test construction path: the explicit
    timestamp (spec default or override) is injected through a frozen clock,
    clearly separated from the normal Observer API, which captures time from
    the system clock.
    """
    source = LocalJsonCatalogSource(catalog_path, snapshot=spec.snapshot)
    timestamp = observed_at if observed_at is not None else spec.observed_at
    observer = Observer(source, clock=FixedUtcClock(parse_rfc3339_utc(timestamp)))
    return observer.observe(
        subject_type=_SUBJECT_TYPE,
        tenant_id=_TENANT,
        resource=_RESOURCE,
        entity_id=_SKU,
        field=_FIELD,
    )


def render_envelope(envelope: dict[str, Any]) -> str:
    """Serialize an envelope to its canonical on-disk fixture form."""
    return json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
