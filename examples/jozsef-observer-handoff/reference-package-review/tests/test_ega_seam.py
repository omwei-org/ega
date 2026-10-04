"""AT-13, AT-16, INV-08: seam semantics preservation, fail-closed validation, EGA status."""

from __future__ import annotations

import copy
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import ROOT
from ega_evaluation_harness import (
    EVALUATION_TIME,
    ExecutionBoundaryStub,
    check_freshness,
    check_value_condition,
)
from nextone_interop.canonical import build_integrity, verify_integrity
from nextone_interop.ega_seam import EgaSeamAdapter
from nextone_interop.evidence import derive_evidence_id, forbidden_semantics_present
from nextone_interop.validation import validate_envelope

EGA_BASELINE_COMMIT = "12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7"
EGA_COMPATIBILITY_DOC = ROOT / "docs" / "EGA_COMPATIBILITY.md"


def find_ega_repo() -> Path | None:
    candidates = []
    env = os.environ.get("NEXTONE_EGA_REPO")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            ROOT.parent / "ega",
            ROOT.parent / "nextone-ega",
            ROOT.parent / "EGA",
        ]
    )
    for candidate in candidates:
        if (candidate / ".git").is_dir():
            return candidate
    return None


def test_inv_08_adapter_crossing_preserves_semantics(golden):
    seam = EgaSeamAdapter()
    presented = seam.present(golden)
    assert presented == golden
    assert presented is not golden
    validate_envelope(presented)
    assert forbidden_semantics_present(presented) == []


def test_seam_refuses_evidence_with_authorization_semantics(golden):
    seam = EgaSeamAdapter()
    poisoned = copy.deepcopy(golden)
    # Nested inside observed_value so the object is schema-valid: the denial
    # must come from step 2 (forbidden semantics), not from step 1 (schema).
    poisoned["observed_value"] = {"authorized_price": 2500}
    poisoned["integrity"] = build_integrity(poisoned)
    assert verify_integrity(poisoned) is True
    with pytest.raises(ValueError, match="authorization semantics"):
        seam.present(poisoned)


def test_seam_refuses_tampered_evidence(golden):
    seam = EgaSeamAdapter()
    tampered = copy.deepcopy(golden)
    tampered["observed_value"] = 2600
    # Re-derive the id so the object is identity-consistent and actually
    # reaches step 3; the stale digest (not recomputed) is what must reject it.
    tampered["evidence_id"] = derive_evidence_id(
        subject=tampered["subject"],
        target=tampered["target"],
        observed_state=tampered["observed_state"],
        observed_value=tampered["observed_value"],
        observed_at=tampered["observed_at"],
        provenance=tampered["provenance"],
    )
    assert verify_integrity(tampered) is False
    with pytest.raises(ValueError, match="integrity"):
        seam.present(tampered)


def test_seam_accepts_golden_envelope(golden):
    seam = EgaSeamAdapter()
    presented = seam.present(golden)
    assert presented == golden
    assert verify_integrity(presented) is True


def test_seam_rejects_missing_required_field_even_with_recomputed_digest(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    del broken["uncertainty"]
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True, (
        "digest is correct for the malformed payload, so rejection must come "
        "from the schema step, not from integrity"
    )
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


def test_seam_rejects_invalid_observed_state(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["observed_state"] = "VERIFIED"
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


def test_seam_rejects_unknown_state_with_non_null_value(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["observed_state"] = "UNKNOWN"
    broken["observed_value"] = 2500
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


def test_seam_rejects_known_state_with_null_value(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["observed_value"] = None
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


def test_seam_rejects_invalid_observed_at(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["observed_at"] = "yesterday-ish"
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


# Timestamp-validation refinement: the schema validates observed_at semantically, not
# just by string shape. These timestamps match the UTC-Z shape but encode
# impossible calendar/time values; every envelope carries a correctly
# recomputed digest, so rejection must come from step 1 (schema validation
# with active date-time format checking), not from integrity.
IMPOSSIBLE_OBSERVED_AT = [
    "2026-02-30T12:00:00Z",  # February 30 does not exist
    "2026-13-01T00:00:00Z",  # month 13 does not exist
    "2026-10-03T25:00:00Z",  # hour 25 does not exist
    "2026-99-99T99:99:99Z",  # out-of-range everywhere
]


@pytest.mark.parametrize("observed_at", IMPOSSIBLE_OBSERVED_AT)
def test_seam_rejects_impossible_observed_at_even_with_recomputed_digest(golden, observed_at):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["observed_at"] = observed_at
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True, (
        "digest is correct for the impossible-timestamp payload, so rejection "
        "must come from semantic schema validation, not from integrity"
    )
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


def test_seam_rejects_non_leap_year_february_29(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["observed_at"] = "2026-02-29T12:00:00Z"  # 2026 is not a leap year
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="not a valid EvidenceEnvelope"):
        seam.present(broken)


def test_seam_accepts_leap_year_february_29(golden):
    seam = EgaSeamAdapter()
    leap = copy.deepcopy(golden)
    leap["observed_at"] = "2024-02-29T12:00:00Z"  # 2024 is a leap year
    leap["evidence_id"] = derive_evidence_id(
        subject=leap["subject"],
        target=leap["target"],
        observed_state=leap["observed_state"],
        observed_value=leap["observed_value"],
        observed_at=leap["observed_at"],
        provenance=leap["provenance"],
    )
    leap["integrity"] = build_integrity(leap)
    assert verify_integrity(leap) is True
    presented = seam.present(leap)
    assert presented["observed_at"] == "2024-02-29T12:00:00Z"


def test_seam_accepts_golden_observed_at_semantically(golden):
    """Positive coverage: the golden fixture timestamp stays valid under the
    active date-time format check."""
    seam = EgaSeamAdapter()
    presented = seam.present(golden)
    validate_envelope(presented)
    assert presented["observed_at"] == "2026-10-03T19:00:00Z"


# Identity-consistency refinement: the schema only checks that evidence_id has
# the ev1:<hex> shape, and integrity verification can succeed after manually
# swapping in another syntactically valid id and recomputing the digest. The
# seam must therefore independently re-derive the expected id from the
# identity fields (derive_evidence_id — the same authoritative function the
# Observer generation path uses) and fail closed on mismatch, before
# integrity verification, never silently repairing the supplied id.
WRONG_SYNTACTICALLY_VALID_ID = "ev1:" + "0" * 64


def test_seam_rejects_syntactically_valid_but_wrong_evidence_id(golden):
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["evidence_id"] = WRONG_SYNTACTICALLY_VALID_ID
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True, (
        "digest is correct for the wrong-id payload, so rejection must come "
        "from evidence_id derivation consistency, not from integrity"
    )
    with pytest.raises(ValueError, match="inconsistent with the observation identity"):
        seam.present(broken)


def _identity_clone(golden, mutate):
    clone = copy.deepcopy(golden)
    mutate(clone)
    clone["evidence_id"] = derive_evidence_id(
        subject=clone["subject"],
        target=clone["target"],
        observed_state=clone["observed_state"],
        observed_value=clone["observed_value"],
        observed_at=clone["observed_at"],
        provenance=clone["provenance"],
    )
    clone["integrity"] = build_integrity(clone)
    return clone


def test_seam_same_timestamp_conflicts_remain_individually_valid(golden):
    """Conflict case: same timestamp, different value/source stay independent,
    keep distinct ids and digests, and both pass identity consistency."""
    seam = EgaSeamAdapter()
    other = _identity_clone(
        golden,
        lambda env: (
            env["observed_value"].update({"amount": 2600})
            if isinstance(env["observed_value"], dict)
            else env.update({"observed_value": 2600}),
            env["provenance"].update({"source_id": "local-catalog-alt"}),
        ),
    )
    golden_presented = seam.present(golden)
    other_presented = seam.present(other)
    assert golden_presented["observed_at"] == other_presented["observed_at"]
    assert golden_presented["evidence_id"] != other_presented["evidence_id"]
    assert golden_presented["integrity"]["digest"] != other_presented["integrity"]["digest"]
    assert verify_integrity(other_presented) is True


IDENTITY_MUTATIONS = [
    pytest.param(
        lambda env: env.update({"observed_value": 2600}),
        id="observed_value",
    ),
    pytest.param(
        lambda env: env["provenance"].update({"source_id": "local-catalog-alt"}),
        id="provenance.source_id",
    ),
    pytest.param(
        lambda env: env.update({"observed_at": "2026-10-03T20:00:00Z"}),
        id="observed_at",
    ),
]


@pytest.mark.parametrize("mutate", IDENTITY_MUTATIONS)
def test_seam_rejects_stale_evidence_id_after_identity_field_change(golden, mutate):
    """Identity field changed, envelope integrity recomputed, old evidence_id
    retained: the supplied id no longer matches the derived identity."""
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    mutate(broken)
    broken["integrity"] = build_integrity(broken)  # old evidence_id kept
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="inconsistent with the observation identity"):
        seam.present(broken)


def test_seam_rejects_provenance_only_mutation_with_old_evidence_id(golden):
    """Source/provenance identity changed, nothing else: still rejected."""
    seam = EgaSeamAdapter()
    broken = copy.deepcopy(golden)
    broken["provenance"]["source_id"] = "local-catalog-alt"
    broken["integrity"] = build_integrity(broken)
    assert verify_integrity(broken) is True
    with pytest.raises(ValueError, match="inconsistent with the observation identity"):
        seam.present(broken)


def test_seam_rejects_non_object_input():
    seam = EgaSeamAdapter()
    with pytest.raises(TypeError, match="EvidenceEnvelope"):
        seam.present(["not", "an", "envelope"])


def test_at_13_authorized_price_is_outside_observer_evidence(ega_authorization_context):
    condition = ega_authorization_context["authorization_condition"]
    assert condition["authorized_value_cents"] == 2500
    assert (ROOT / "tests" / "ega_context" / "authorized_price_2500.json").is_file()
    fixture_paths = sorted((ROOT / "fixtures").rglob("*.json"))
    assert all("ega_context" not in str(p) for p in fixture_paths)
    observer_sources = (ROOT / "src" / "nextone_interop").rglob("*.py")
    for source in observer_sources:
        text = source.read_text(encoding="utf-8")
        assert "ega_context" not in text and "authorized_price_2500" not in text, (
            f"authorization context leaked into {source.name}"
        )


def test_evaluation_time_freshness_decision_lives_on_ega_side(envelopes, ega_authorization_context):
    """Demonstrate the frozen temporal split with a test-only evaluator.

    The Observer labelled nothing FRESH/STALE; the evaluator applies the
    freshness condition at evaluation time (INV-03).
    """
    authorized = ega_authorization_context["authorization_condition"]["authorized_value_cents"]
    golden = envelopes["golden/known_price_2500.json"]
    older = envelopes["negative/older_observation_price_2500.json"]
    mismatch = envelopes["negative/known_price_2600.json"]
    unknown = envelopes["negative/unknown_price.json"]

    max_age = timedelta(hours=1)
    assert check_value_condition(golden, authorized) is True
    assert check_freshness(golden, max_age, EVALUATION_TIME) is True

    assert check_value_condition(older, authorized) is True
    assert check_freshness(older, max_age, EVALUATION_TIME) is False, (
        "same fact + older temporal evidence: freshness fails at evaluation time"
    )

    assert check_value_condition(mismatch, authorized) is False
    assert check_value_condition(unknown, authorized) is False


def test_execution_boundary_stub_is_only_a_recorder(envelopes, ega_authorization_context):
    """Non-ComOS handoff demonstration (the defined scope)."""
    golden = envelopes["golden/known_price_2500.json"]
    authorized = ega_authorization_context["authorization_condition"]["authorized_value_cents"]
    stub = ExecutionBoundaryStub()
    if check_value_condition(golden, authorized) and check_freshness(
        golden, timedelta(hours=1), EVALUATION_TIME
    ):
        stub.record_projected_execution_condition(
            {
                "operation": "retail_sale",
                "basis": "ega_evaluation_of_observer_evidence",
                "evidence_id": golden["evidence_id"],
            }
        )
    assert len(stub.recorded) == 1
    assert "stub" in stub.label


def test_at_16_ega_compatibility_status_is_documented():
    """External compatibility test (AT-16).

    The EGA repository at the baseline commit was not available in this
    workspace, so compatibility could not be executed. Instead of silently
    skipping, this test verifies that docs/EGA_COMPATIBILITY.md records the
    exact baseline commit and the unavailability, keeping the suite honest.
    """
    ega_repo = find_ega_repo()
    doc = EGA_COMPATIBILITY_DOC.read_text(encoding="utf-8")
    assert EGA_BASELINE_COMMIT in doc, "compatibility doc must name the baseline commit"

    if ega_repo is None:
        assert "NOT available" in doc or "unavailable" in doc.lower()
        assert "not executed" in doc.lower()
        return

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ega_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == EGA_BASELINE_COMMIT, (
        f"EGA repo present at {ega_repo} but not at baseline commit "
        f"{EGA_BASELINE_COMMIT} (found {head}); compatibility not executed"
    )
    raise AssertionError(
        "EGA repository is available but no automated contract probe is defined; "
        "extend docs/EGA_COMPATIBILITY.md before claiming compatibility."
    )
