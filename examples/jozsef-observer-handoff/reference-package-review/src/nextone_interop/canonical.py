"""Deterministic canonicalization and integrity digest.

Algorithm ``nextone-canonical-json-v1``:

1. Take the EvidenceEnvelope payload **excluding** the ``integrity`` object.
   The digest input is therefore never self-referential (INV-07, AT-07).
2. Serialize to JSON with deterministic key ordering: object keys sorted by
   Unicode code point, recursively, at every nesting level (AT-05).
3. No insignificant whitespace: compact separators ``,`` and ``:``.
4. Stable primitive representation; text encoded as UTF-8
   (``ensure_ascii=False``).
5. Compute SHA-256 over the resulting bytes; prefix the hex digest with
   ``sha256:``.

Any change to a covered field (observed fact, ``observed_at``, provenance,
subject, target, temporal basis, uncertainty, evidence id, schema version)
changes the digest (AT-06).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

INTEGRITY_FIELD = "integrity"
DIGEST_PREFIX = "sha256:"


def canonicalize(payload: Any) -> bytes:
    """Return the canonical UTF-8 bytes of a JSON-compatible payload."""
    text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return text.encode("utf-8")


def digest_payload(payload: dict[str, Any]) -> str:
    """Compute the SHA-256 integrity digest of an envelope payload.

    The ``integrity`` field is removed before canonicalization so the digest
    never covers itself.
    """
    covered = {k: v for k, v in payload.items() if k != INTEGRITY_FIELD}
    return DIGEST_PREFIX + hashlib.sha256(canonicalize(covered)).hexdigest()


def build_integrity(payload: dict[str, Any]) -> dict[str, str]:
    """Build the integrity object for an envelope payload."""
    return {
        "canonicalization": "nextone-canonical-json-v1",
        "algorithm": "sha256",
        "digest": digest_payload(payload),
    }


def verify_integrity(envelope: dict[str, Any]) -> bool:
    """Recompute the digest of a complete envelope and compare with its own."""
    expected = digest_payload(envelope)
    actual = envelope.get(INTEGRITY_FIELD, {}).get("digest", "")
    return expected == actual
