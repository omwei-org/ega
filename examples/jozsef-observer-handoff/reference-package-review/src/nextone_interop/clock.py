"""Observation-time clock abstraction.

The Observer owns observation-time capture: the normal ``observe()`` API
takes no caller-supplied timestamp. Time comes from an injectable ``Clock``
so tests and deterministic fixture generation can freeze it (corrective
pass, Correction 3).

* ``SystemUtcClock`` — default clock backed by the system clock, normalized
  to timezone-aware UTC.
* ``FixedUtcClock`` — frozen clock for tests and deterministic fixture
  construction only; clearly separated from normal Observer use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

# Strict RFC 3339 UTC form used by evidence ``observed_at`` values (Z suffix,
# no numeric offset). Mirrors the JSON Schema pattern.
RFC3339_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class Clock(Protocol):
    """Source of observation time."""

    def now_utc(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


@dataclass(frozen=True)
class SystemUtcClock:
    """Default clock backed by the system clock, normalized to UTC."""

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FixedUtcClock:
    """Frozen clock for tests and deterministic fixture construction only."""

    fixed: datetime

    def __post_init__(self) -> None:
        if self.fixed.tzinfo is None or self.fixed.utcoffset() is None:
            raise ValueError("FixedUtcClock requires a timezone-aware datetime, got a naive one")

    def now_utc(self) -> datetime:
        return self.fixed


def format_rfc3339_utc(value: datetime) -> str:
    """Format a timezone-aware datetime as strict RFC 3339 UTC (``...Z``)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime cannot become observation time; timezone-aware UTC required")
    utc = value.astimezone(timezone.utc)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    if utc.microsecond:
        text += f".{utc.microsecond:06d}"
    return text + "Z"


def parse_rfc3339_utc(text: str) -> datetime:
    """Parse a strict RFC 3339 UTC timestamp (the evidence ``observed_at`` form)."""
    if not isinstance(text, str) or not RFC3339_UTC_PATTERN.match(text):
        raise ValueError(f"not a strict RFC 3339 UTC timestamp: {text!r}")
    return datetime.fromisoformat(text[:-1] + "+00:00")
