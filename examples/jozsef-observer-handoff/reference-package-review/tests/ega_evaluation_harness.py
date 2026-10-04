"""Test-only EGA-side evaluation harness. NOT part of the Observer package.

This module exists solely to demonstrate, inside tests, what EGA-side
evaluation does with Observer evidence: it checks an independently
established authorization condition against the evidence at evaluation
time. It is a local stand-in for EGA evaluation semantics, clearly labeled
as such; it is not the real EGA and not ComOS (INV-12: no fake integration
results are claimed).

Nothing here is imported by src/nextone_interop (AT-11, AT-13).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

EVALUATION_TIME = datetime(2026, 10, 3, 19, 30, 0, tzinfo=timezone.utc)


def parse_utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def check_value_condition(evidence: dict[str, Any], authorized_value_cents: int) -> bool:
    """Does the observed value equal the independently authorized value?"""
    if evidence["observed_state"] != "KNOWN":
        return False
    return evidence["observed_value"] == authorized_value_cents


def check_freshness(
    evidence: dict[str, Any],
    max_age: timedelta,
    evaluated_at: datetime = EVALUATION_TIME,
) -> bool:
    """Does the evidence satisfy the applicable freshness condition?

    This decision is made HERE, at evaluation time, by the evaluator —
    never by the Observer (INV-03).
    """
    observed_at = parse_utc(evidence["observed_at"])
    return evaluated_at - observed_at <= max_age


class ExecutionBoundaryStub:
    """Non-ComOS test boundary demonstrating the handoff contract only.

    It records that a projected execution condition reached the boundary;
    it performs no protected operation, creates no order, and must never be
    presented as validated ComOS execution (see docs/ARCHITECTURE.md).
    """

    label = "non-ComOS test execution boundary stub"

    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def record_projected_execution_condition(self, projection: dict[str, Any]) -> None:
        self.recorded.append(dict(projection))
