"""Narrow EGA seam adapter.

Purpose: present Observer evidence to the EGA adapter contract without
changing its meaning (INV-08). Crossing this interface must not promote an
observation into an AEE, an authorization basis, policy-condition
satisfaction, a commit condition, or any execution authority.

EGA compatibility status: the EGA repository at commit
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7 was NOT available in the workspace
used to build this reference, so the exact EGA-side adapter contract could
not be inspected. This seam therefore performs a strictly lossless
presentation of the EvidenceEnvelope and refuses to hand over objects that
fail validation. What remains unverified is recorded in
docs/EGA_COMPATIBILITY.md (INV-12: missing contracts are reported, not
invented).

Fail-closed handoff pipeline (validation refinement, Correction 1); a failure at
any step rejects the object with a precise local error and no seam handoff
representation is created — nothing is silently repaired:

1. EvidenceEnvelope v1 JSON Schema validation — the authoritative structural
   contract, so a malformed object cannot pass merely because it carries a
   valid digest for its malformed payload (including the semantic RFC 3339
   date-time check on ``observed_at``);
2. forbidden-semantic / architectural-invariant validation — the recursive
   denylist scan for authorization semantics the schema cannot express at
   arbitrary depth, plus ``evidence_id`` derivation consistency: the seam
   independently re-derives the expected identifier from the envelope's
   identity fields with the same authoritative ``derive_evidence_id`` used by
   the Observer and compares it to the supplied id (final identity-hardening
   pass). A mismatch fails closed — the id is never silently repaired,
   overwritten, or regenerated;
3. canonical integrity verification — the object must hash to its own
   documented digest (INV-07);
4. presentation / handoff — a semantics-preserving deep copy (INV-08).
"""

from __future__ import annotations

import copy
from typing import Any

import jsonschema

from .canonical import verify_integrity
from .evidence import derive_evidence_id, forbidden_semantics_present
from .validation import validate_envelope

# Fields that would turn evidence into authority if added by the seam.
_SEAM_FORBIDDEN_ADDITIONS = (
    "authorized_price",
    "expected_price",
    "predicate_result",
    "AEE",
    "authorization_basis",
    "commit_condition",
    "execution_authority",
    "policy_satisfaction",
    "projected_execution_condition",
)


class EgaSeamAdapter:
    """Presents Observer evidence across the evaluation seam, unchanged.

    ``present()`` is fail-closed and validates in the documented pipeline
    order: schema, forbidden semantics, integrity, then handoff. The returned
    object is a deep copy: the seam neither adds nor removes semantics, so
    downstream evaluation sees exactly the same claim the Observer recorded.
    """

    def present(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Validate then hand over the evidence object, unmodified."""
        self._validate_schema(envelope)
        self._check_evidence_only(envelope)
        self._check_identity_consistency(envelope)
        self._verify_integrity(envelope)
        return copy.deepcopy(envelope)

    def present_all(self, envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Present several independent observations without merging them.

        Conflicting observations stay independent (INV-06, AT-10): the seam
        performs no resolution, no winner selection, no averaging, and emits
        no synthetic conflict-resolution observation.
        """
        return [self.present(envelope) for envelope in envelopes]

    @staticmethod
    def _validate_schema(envelope: dict[str, Any]) -> None:
        if not isinstance(envelope, dict):
            raise TypeError("seam input must be an EvidenceEnvelope object")
        try:
            validate_envelope(envelope)
        except jsonschema.ValidationError as exc:
            raise ValueError(
                "seam input is not a valid EvidenceEnvelope v1: "
                f"{exc.message} (instance path: {list(exc.absolute_path)})"
            ) from exc

    @staticmethod
    def _check_evidence_only(envelope: dict[str, Any]) -> None:
        leaks = forbidden_semantics_present(envelope)
        if leaks:
            raise ValueError(
                "evidence carries authorization semantics, seam refuses to "
                f"present it: {leaks}"
            )

    @staticmethod
    def _check_identity_consistency(envelope: dict[str, Any]) -> None:
        """Re-derive the expected evidence_id from the identity fields.

        Uses the same authoritative ``derive_evidence_id`` as the Observer
        generation path, so verification semantics cannot diverge from
        generation semantics. A supplied id that merely matches the schema's
        ``ev1:<hex>`` shape but is not the deterministic derivation fails
        closed here — before integrity verification, which must not be usable
        to rescue an identity mismatch. The supplied id is never repaired,
        overwritten, or regenerated.
        """
        expected = derive_evidence_id(
            subject=envelope["subject"],
            target=envelope["target"],
            observed_state=envelope["observed_state"],
            observed_value=envelope["observed_value"],
            observed_at=envelope["observed_at"],
            provenance=envelope["provenance"],
        )
        if envelope["evidence_id"] != expected:
            raise ValueError(
                "evidence_id is inconsistent with the observation identity "
                f"fields: supplied {envelope['evidence_id']!r}, re-derived "
                f"{expected!r}; seam refuses to present it"
            )

    @staticmethod
    def _verify_integrity(envelope: dict[str, Any]) -> None:
        if not verify_integrity(envelope):
            raise ValueError("evidence integrity digest does not verify")
