"""Read-only catalog source abstraction.

The Observer reads observed values exclusively through this interface
(AT-14). The default implementation reads a clearly labeled local JSON
catalog fixture; it is NOT real ComOS. The interface is kept small so a real
read-only ComOS adapter can replace the fixture later without touching the
Observer (see docs/ARCHITECTURE.md, section "Catalog source").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class CatalogSource(Protocol):
    """Read-only catalog source."""

    def read_field(self, tenant_id: str, sku: str, field: str) -> Any | None:
        """Return the observed field value, or None when not present.

        Implementations must not mutate the observed system (INV-02).
        """
        ...

    def describe(self) -> "SourceDescriptor":
        """Return stable provenance identity for observations from this source."""
        ...


@dataclass(frozen=True)
class SourceDescriptor:
    source_id: str
    source_kind: str
    source_locator_prefix: str


class LocalJsonCatalogSource:
    """Deterministic read-only source backed by a local catalog fixture file.

    The fixture shape is::

        {
          "description": "...",
          "source_id": "<default source id>",
          "locator_prefix": "<default locator prefix>",
          "snapshots": {
            "<snapshot>": {
              "provenance": {
                "source_id": "<optional override>",
                "locator_prefix": "<optional override>"
              },
              "data": {
                "<tenant_id>": {"<sku>": {"<field>": <value>, ...}, ...},
                ...
              }
            },
            ...
          }
        }

    A source is bound to one snapshot. Values are read with plain dict
    lookups; missing keys yield None, which the Observer reports as UNKNOWN.
    """

    def __init__(self, path: str | Path, snapshot: str = "current") -> None:
        self._path = Path(path)
        self._snapshot = snapshot
        data = json.loads(self._path.read_text(encoding="utf-8"))
        snapshots = data.get("snapshots", {})
        if snapshot not in snapshots:
            raise KeyError(f"snapshot {snapshot!r} not in {self._path}")
        raw = snapshots[snapshot]
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), dict):
            raise ValueError(f"snapshot {snapshot!r} in {self._path} must be an object with a 'data' object")
        self._data = raw["data"]
        override = raw.get("provenance", {})
        self._descriptor = SourceDescriptor(
            source_id=override.get("source_id", data.get("source_id", "local-catalog")),
            source_kind="local_catalog",
            source_locator_prefix=override.get("locator_prefix", data.get("locator_prefix", "catalog")),
        )

    @property
    def snapshot(self) -> str:
        return self._snapshot

    def describe(self) -> SourceDescriptor:
        return self._descriptor

    def read_field(self, tenant_id: str, sku: str, field: str) -> Any | None:
        tenant = self._data.get(tenant_id)
        if not isinstance(tenant, dict):
            return None
        entry = tenant.get(sku)
        if not isinstance(entry, dict):
            return None
        return entry.get(field)
