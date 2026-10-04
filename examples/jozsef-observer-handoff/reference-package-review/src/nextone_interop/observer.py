"""Minimal evidence-only Observer.

The Observer is read-only, evidentiary, non-authoritative, non-executing:

* it reports what it observed, from which source, at which time;
* it captures the observation time itself, from its clock (validation refinement,
  Correction 3) — callers cannot inject arbitrary timestamps through the
  normal API;
* it never decides whether an action is allowed;
* it never emits FRESH/STALE (INV-03), ALLOW/DENY, or HOLD/ESCALATE/REFUSE;
* it never joins the protected execution path (INV-09).

Intentionally, this module defines no method named authorize, approve, allow,
deny, execute, commit, grant, resolve_policy or evaluate_policy (AT-11, AT-12).
"""

from __future__ import annotations

from typing import Any

from .canonical import build_integrity
from .catalog_source import CatalogSource
from .clock import (
    RFC3339_UTC_PATTERN,
    Clock,
    SystemUtcClock,
    format_rfc3339_utc,
)
from .evidence import (
    OBSERVED_KNOWN,
    OBSERVED_UNKNOWN,
    derive_evidence_id,
)

_TEMPORAL_BASIS = {
    "type": "point_in_time",
    "timestamp_semantics": "observation_completed_at",
    "clock": "UTC",
}


class Observer:
    """Read-only observation collector producing EvidenceEnvelope objects.

    The clock dependency is injectable so tests and deterministic fixture
    construction can freeze time with ``FixedUtcClock``. Normal use leaves it
    unset and the Observer reads the system UTC clock at the moment the
    observation is captured.
    """

    def __init__(self, source: CatalogSource, *, clock: Clock | None = None) -> None:
        self._source = source
        self._clock: Clock = clock if clock is not None else SystemUtcClock()

    def observe(
        self,
        *,
        subject_type: str,
        tenant_id: str,
        resource: str,
        entity_id: str,
        field: str,
    ) -> dict[str, Any]:
        """Observe one target and return a complete EvidenceEnvelope.

        ``observed_at`` is captured from this Observer's clock at observation
        time; the caller cannot supply an arbitrary timestamp through this
        normal API. The envelope carries the time as temporal evidence only.
        Whether the evidence satisfies an applicable freshness condition is
        decided solely by EGA at evaluation time (INV-03).

        Deterministic fixture/historical construction is a clearly separated
        path: it injects a ``FixedUtcClock`` (see ``nextone_interop.clock``)
        and still flows through this same method.
        """
        observed_at = format_rfc3339_utc(self._clock.now_utc())
        return self._build_envelope(
            subject_type=subject_type,
            tenant_id=tenant_id,
            resource=resource,
            entity_id=entity_id,
            field=field,
            observed_at=observed_at,
        )

    def _build_envelope(
        self,
        *,
        subject_type: str,
        tenant_id: str,
        resource: str,
        entity_id: str,
        field: str,
        observed_at: str,
    ) -> dict[str, Any]:
        """Assemble the envelope for one already-fixed observation time.

        Private assembly shared by ``observe()`` (clock-captured time) and
        the deterministic fixture/test construction path. The timestamp is
        re-validated here so malformed values cannot enter the evidence path
        even through internal callers. Not part of the public API (AT-11).
        """
        if not isinstance(observed_at, str) or not RFC3339_UTC_PATTERN.match(observed_at):
            raise ValueError(
                f"observed_at must be a strict RFC 3339 UTC timestamp, got {observed_at!r}"
            )

        value = self._source.read_field(tenant_id, entity_id, field)
        descriptor = self._source.describe()

        subject = {"type": subject_type, "id": tenant_id}
        target = {"resource": resource, "entity_id": entity_id, "field": field}
        provenance = {
            "source_id": descriptor.source_id,
            "source_kind": descriptor.source_kind,
            "collection_method": "read_only",
            "source_locator": f"{descriptor.source_locator_prefix}/{tenant_id}/{entity_id}/{field}",
        }
        observed_state = OBSERVED_UNKNOWN if value is None else OBSERVED_KNOWN

        envelope: dict[str, Any] = {
            "schema_version": "nextone.observer.evidence-envelope/1.0",
            "evidence_id": derive_evidence_id(
                subject=subject,
                target=target,
                observed_state=observed_state,
                observed_value=value,
                observed_at=observed_at,
                provenance=provenance,
            ),
            "subject": subject,
            "target": target,
            "observed_state": observed_state,
            "observed_value": value,
            "observed_at": observed_at,
            "temporal_basis": dict(_TEMPORAL_BASIS),
            "provenance": provenance,
            # Confidence is never invented: when the source supplies none,
            # the absence is represented explicitly.
            "uncertainty": {
                "source_confidence": None,
                "confidence_semantics": "not_supplied",
            },
        }
        envelope["integrity"] = build_integrity(envelope)
        return envelope
