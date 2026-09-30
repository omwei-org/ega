from __future__ import annotations

from dataclasses import dataclass

from .models import EvidenceItem


@dataclass(frozen=True)
class AEECondition:
    """Minimal semantic seam for an EGA-projected execution condition.

    The condition is intentionally narrow and deterministic. It describes
    properties that must remain true at the execution boundary; it does not
    assign materiality or define governance policy.
    """

    condition_id: str
    evidence_ref: str
    state_equals: str | None = None
    freshness_equals: str | None = None
    uncertainty_max: float | None = None


@dataclass(frozen=True)
class ConditionEvaluation:
    condition_id: str
    status: str
    reason: str


def _validate_condition(condition: AEECondition) -> None:
    if not condition.condition_id:
        raise ValueError("condition_id is required")
    if not condition.evidence_ref:
        raise ValueError("evidence_ref is required")
    if (
        condition.state_equals is None
        and condition.freshness_equals is None
        and condition.uncertainty_max is None
    ):
        raise ValueError("AEE condition must contain at least one predicate")
    if condition.uncertainty_max is not None and not 0.0 <= condition.uncertainty_max <= 1.0:
        raise ValueError("uncertainty_max must be between 0 and 1")


def evaluate_aee_condition(
    condition: AEECondition,
    evidence: EvidenceItem,
) -> ConditionEvaluation:
    """Evaluate the EGA-defined predicate against current evidence.

    Evidence identity/integrity is separate from predicate semantics:
    a changed evidence digest does not fail a condition when the predicate
    remains true.
    """
    _validate_condition(condition)

    if evidence.evidence_ref != condition.evidence_ref:
        return ConditionEvaluation(
            condition.condition_id,
            "FAILED",
            "EVIDENCE_REF_MISMATCH",
        )

    if condition.state_equals is not None and evidence.state != condition.state_equals:
        return ConditionEvaluation(
            condition.condition_id,
            "FAILED",
            "STATE_MISMATCH",
        )

    if (
        condition.freshness_equals is not None
        and evidence.freshness != condition.freshness_equals
    ):
        return ConditionEvaluation(
            condition.condition_id,
            "FAILED",
            "FRESHNESS_MISMATCH",
        )

    if condition.uncertainty_max is not None:
        if evidence.uncertainty is None:
            return ConditionEvaluation(
                condition.condition_id,
                "FAILED",
                "UNCERTAINTY_UNAVAILABLE",
            )
        if evidence.uncertainty > condition.uncertainty_max:
            return ConditionEvaluation(
                condition.condition_id,
                "FAILED",
                "UNCERTAINTY_MAX_EXCEEDED",
            )

    return ConditionEvaluation(condition.condition_id, "VALID", "PREDICATE_HOLDS")
