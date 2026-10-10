"""Fail-closed EGA HTTP gate for callers integrating with ComOS.

This module does not modify ComOS and cannot force an unmodified ComOS path to
call it. The ComOS adapter must invoke authorize_before_effect before its first
protected effect, then perform the effect only if the returned permit is accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import requests


class EGAAuthorizationDenied(RuntimeError):
    """Raised whenever EGA does not return an unambiguous allow decision."""


@dataclass(frozen=True)
class EGAPermit:
    decision: str
    reason: str
    applied: bool
    effect: str


class EGAHTTPGate:
    """Call EGA's real HTTP endpoint and fail closed on every ambiguity."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", *,
                 timeout_seconds: float = 3.0,
                 session: requests.Session | None = None) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def authorize_before_effect(self, *, authority: Mapping[str, Any],
                                intent: Mapping[str, Any], context_epoch: int,
                                evidence_envelopes: list[Mapping[str, Any]] | None = None) -> EGAPermit:
        """Return a permit only for a well-formed explicit COMMIT response."""
        payload: dict[str, Any] = {
            "authority": dict(authority),
            "intent": dict(intent),
            "context_epoch": context_epoch,
        }
        if evidence_envelopes is not None:
            payload["intent"]["evidence_envelopes"] = list(evidence_envelopes)

        try:
            response = self.session.post(
                f"{self.base_url}/v1/evaluate", json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise EGAAuthorizationDenied("EGA unavailable or response invalid; denied") from exc

        if not isinstance(body, dict):
            raise EGAAuthorizationDenied("EGA response is not an object; denied")
        decision, reason = body.get("decision"), body.get("reason")
        applied, effect = body.get("applied"), body.get("effect")
        if (decision != "COMMIT" or applied is not True
                or effect not in ("NONE", "NOT_EXECUTED")
                or not isinstance(reason, str) or not reason):
            raise EGAAuthorizationDenied("EGA did not return an explicit valid COMMIT; denied")
        return EGAPermit(decision=decision, reason=reason, applied=applied, effect=effect)

    def run_if_authorized(self, effect_callable, *, authority: Mapping[str, Any],
                          intent: Mapping[str, Any], context_epoch: int,
                          evidence_envelopes: list[Mapping[str, Any]] | None = None):
        """Call effect_callable only after a valid COMMIT response.

        The caller must bind the callback to exactly the parameters represented
        by intent; do not authorize one payload and execute another.
        """
        permit = self.authorize_before_effect(
            authority=authority, intent=intent, context_epoch=context_epoch,
            evidence_envelopes=evidence_envelopes,
        )
        return effect_callable(), permit
