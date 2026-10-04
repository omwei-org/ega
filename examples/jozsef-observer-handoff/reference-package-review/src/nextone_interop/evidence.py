"""Shared EvidenceEnvelope semantics.

Constants and helpers that define what an evidence object is — and the
authorization semantics that must never appear inside one (INV-01, INV-04).
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .canonical import canonicalize

OBSERVED_KNOWN = "KNOWN"
OBSERVED_UNKNOWN = "UNKNOWN"

EVIDENCE_ID_PREFIX = "ev1:"
IDENTITY_PAYLOAD_VERSION = 1

# Keys that would leak authorization/policy/execution semantics into evidence.
# Their presence anywhere in an envelope is a contract violation.
FORBIDDEN_SEMANTIC_KEYS: frozenset[str] = frozenset(
    {
        "authorized_price",
        "expected_price",
        "predicate_result",
        "FRESH",
        "STALE",
        "ALLOW",
        "DENY",
        "HOLD",
        "ESCALATE",
        "REFUSE",
        "AEE",
        "authorization",
        "authorization_basis",
        "execution_authority",
        "commit_authority",
        "commit_condition",
        "policy_satisfaction",
        "projected_commit_condition",
        "projected_execution_condition",
    }
)


def iter_keys(node: Any) -> Iterable[str]:
    """Yield every object key in a JSON-compatible structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from iter_keys(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from iter_keys(item)


def forbidden_semantics_present(envelope: Any) -> list[str]:
    """Return the sorted list of forbidden semantic keys found in an object."""
    return sorted(set(iter_keys(envelope)) & FORBIDDEN_SEMANTIC_KEYS)


def derive_evidence_id(
    *,
    subject: dict[str, Any],
    target: dict[str, Any],
    observed_state: str,
    observed_value: Any,
    observed_at: str,
    provenance: dict[str, Any],
) -> str:
    """Deterministically derive a strong observation identifier.

    ``evidence_id = "ev1:" + SHA-256(identity payload)`` where the identity
    payload covers subject, target, observed state, observed value,
    observation time, and provenance — canonically serialized with
    ``nextone-canonical-json-v1``. Two materially different observations
    (different source, state, value, or time) cannot collide on the same id
    merely by sharing subject, target, and timestamp — the weakness of the
    pre-correction derivation.

    The identity payload is documented separately from the full-envelope
    integrity payload in docs/EVIDENCE_CONTRACT.md. The final
    ``integrity.digest`` is never used as the ``evidence_id`` (different
    input, different purpose), the derivation has no recursive dependency on
    the envelope, and it includes no EGA authorization state.
    """
    identity_payload = {
        "identity_version": IDENTITY_PAYLOAD_VERSION,
        "subject": subject,
        "target": target,
        "observed_state": observed_state,
        "observed_value": observed_value,
        "observed_at": observed_at,
        "provenance": provenance,
    }
    digest = hashlib.sha256(canonicalize(identity_payload)).hexdigest()
    return EVIDENCE_ID_PREFIX + digest
