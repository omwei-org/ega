"""
EGA HTTP Service for ComOS Integration

This service provides an HTTP API for evaluating RuntimeIntent against
ExecutionAuthority using the existing EGA core functions.

Architecture:
- POST /v1/evaluate endpoint
- Uses existing EGA functions: prepare(), final_authority_check(), commit()
- Distinguishes authority issuance from evaluation
- Rejects malformed/invalid authority

Security features (v0.1.3):
- Ed25519 authority signatures verified against configured trusted public keys\n- Signed authorities require an expiry interval and matching service audience
- Evaluation disabled by default when no trusted verification keys are configured
- AEE conditions require Observer v1 evidence or block
- Evidence converted using existing observer_v1_envelope_to_evidence()
- AEE conditions evaluated against converted evidence
- Independent context epoch from system time (staleness detection)
- Binds to 127.0.0.1 by default
- Generic error messages (no internal details leaked)
- HTTP authentication not implemented (requires network security layer)

Security limitations (v0.1.3 - ARCHITECTURAL):
- Authority expiry/revocation and replay protection are not implemented
- Revocation and replay protection are not implemented
- No replay protection (not in EGA models)
- Public keys must be provisioned out-of-band; no authority issuance or key rotation API
- These require EGA core model changes, not service-layer changes

Configuration:
- EGA_HOST: Bind address (default: 127.0.0.1)
- EGA_PORT: Port (default: 8000)
- EGA_AUTHORITY_PUBLIC_KEYS_JSON: JSON map of authority IDs to base64 raw Ed25519 public keys (default: empty)
- EGA_FAIL_CLOSED: Reject unknown IDs in unsafe test mode (default: true)
- EGA_ALLOW_UNVERIFIED_AUTHORITY: Explicitly unsafe test/demo bypass if no keys are configured (default: false)
- EGA_MAX_CONTEXT_AGE_SECONDS: Max allowed age for context epoch (default: 300)\n- EGA_MAX_AUTHORITY_TTL_SECONDS: Maximum signed authority lifetime (default: 300)\n- EGA_AUTHORITY_CLOCK_SKEW_SECONDS: Allowed future issue-time skew (default: 5)\n- EGA_SERVICE_AUDIENCE: Required authority audience (default: ega-service)

Usage:
  # Default: evaluation remains disabled until authority authenticity verification exists
  python3 -m ega.service

  # UNSAFE model/demo mode only; never use with real ComOS or production traffic
  EGA_FAIL_CLOSED=false EGA_ALLOW_UNVERIFIED_AUTHORITY=true python3 -m ega.service
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
import uvicorn
import os
import time
from datetime import datetime, timezone

from .models import RuntimeIntent, ExecutionAuthority, EvidenceItem
from .boundary import prepare, final_authority_check, commit
from .authority import AuthorizationError
from .interop import observer_v1_envelope_to_evidence


# Configuration
DEFAULT_HOST = os.getenv("EGA_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("EGA_PORT", "8000"))
TRUSTED_AUTHORITY_IDS: Set[str] = set(
    os.getenv("EGA_TRUSTED_AUTHORITY_IDS", "").split(",") if os.getenv("EGA_TRUSTED_AUTHORITY_IDS") else []
)
FAIL_CLOSED_ON_UNKNOWN_AUTHORITY = os.getenv("EGA_FAIL_CLOSED", "true").lower() == "true"
# The HTTP request carries caller-supplied authority fields; an ID whitelist
# does not authenticate those fields. Unsafe model/demo mode must be explicit.
ALLOW_UNVERIFIED_AUTHORITY = os.getenv("EGA_ALLOW_UNVERIFIED_AUTHORITY", "false").lower() == "true"
MAX_CONTEXT_AGE_SECONDS = int(os.getenv("EGA_MAX_CONTEXT_AGE_SECONDS", "300"))  # 5 minutes default
MAX_AUTHORITY_TTL_SECONDS = int(os.getenv("EGA_MAX_AUTHORITY_TTL_SECONDS", "300"))
AUTHORITY_CLOCK_SKEW_SECONDS = int(os.getenv("EGA_AUTHORITY_CLOCK_SKEW_SECONDS", "5"))
SERVICE_AUDIENCE = os.getenv("EGA_SERVICE_AUDIENCE", "ega-service")


# Pydantic models for request/response validation

class ItemsItem(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)

class Parameters(BaseModel):
    items: list[ItemsItem]
    expected_total_coms: Optional[int] = None

class RuntimeIntentRequest(BaseModel):
    principal: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    parameters: Parameters
    environment: str = Field(..., min_length=1)
    decision_ref: Optional[str] = None
    governance_context: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None  # Accept plain dict for backward compatibility
    evidence_envelopes: Optional[list[EvidenceEnvelopeRequest]] = None  # Observer v1 envelopes

class EvidenceEnvelopeRequest(BaseModel):
    """Observer v1 evidence envelope."""
    schema_version: str
    evidence_id: str
    subject: Dict[str, Any]
    target: Dict[str, Any]
    observed_state: str
    observed_value: Any
    observed_at: str
    temporal_basis: Dict[str, Any]
    provenance: Dict[str, Any]
    uncertainty: Optional[Dict[str, Any]] = None
    integrity: Dict[str, Any]

class AEEConditionRequest(BaseModel):
    condition_id: str
    evidence_ref: str
    state_equals: Optional[str] = None
    freshness_equals: Optional[str] = None
    uncertainty_max: Optional[float] = None
    value_equals: Optional[Any] = None
    condition_id: str
    evidence_ref: str
    state_equals: Optional[str] = None
    freshness_equals: Optional[str] = None
    uncertainty_max: Optional[float] = None
    value_equals: Optional[Any] = None

class ExecutionAuthorityRequest(BaseModel):
    authority_id: str = Field(..., min_length=1)
    principal: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    parameters: Dict[str, Any]
    environment: str = Field(..., min_length=1)
    source_decision: str = Field(..., min_length=1)
    signature: Optional[str] = None  # Base64 Ed25519 signature over canonical authority fields
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    audience: Optional[str] = None
    governance_context: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    status: str = "VALID"
    ao_ref: Optional[str] = None
    aee_ref: Optional[str] = None
    ect_ref: Optional[str] = None
    decision_record_ref: Optional[str] = None
    decision_record_digest: Optional[str] = None
    aee_conditions: Optional[list[AEEConditionRequest]] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v != "VALID":
            raise ValueError('only VALID status is accepted for evaluation')
        return v

class EvaluateRequest(BaseModel):
    intent: RuntimeIntentRequest
    authority: ExecutionAuthorityRequest
    context_epoch: int

class EvaluateResponse(BaseModel):
    decision: str  # "COMMIT" or "BLOCK"
    reason: str
    applied: bool
    effect: str  # "NOT_EXECUTED" or "NONE"


# FastAPI app
app = FastAPI(
    title="EGA Service",
    description="HTTP API for EGA → ComOS integration",
    version="0.1.3"
)


def _convert_intent(request: RuntimeIntentRequest) -> RuntimeIntent:
    """Convert Pydantic request to EGA RuntimeIntent model."""
    return RuntimeIntent(
        principal=request.principal,
        action=request.action,
        target=request.target,
        parameters={
            "items": [
                {"product_id": item.product_id, "quantity": item.quantity}
                for item in request.parameters.items
            ],
            **({"expected_total_coms": request.parameters.expected_total_coms}
               if request.parameters.expected_total_coms is not None else {})
        },
        environment=request.environment,
        decision_ref=request.decision_ref or "",
        governance_context=request.governance_context or {},
        evidence=request.evidence or {}
    )


def _convert_authority(request: ExecutionAuthorityRequest) -> ExecutionAuthority:
    """Convert Pydantic request to EGA ExecutionAuthority model."""
    # Convert AEE conditions
    aee_conditions = ()
    if request.aee_conditions:
        from .models import AEECondition
        aee_conditions = tuple(
            AEECondition(
                condition_id=cond.condition_id,
                evidence_ref=cond.evidence_ref,
                state_equals=cond.state_equals,
                freshness_equals=cond.freshness_equals,
                uncertainty_max=cond.uncertainty_max,
                value_equals=cond.value_equals
            )
            for cond in request.aee_conditions
        )

    return ExecutionAuthority(
        authority_id=request.authority_id,
        principal=request.principal,
        action=request.action,
        target=request.target,
        parameters=request.parameters,
        environment=request.environment,
        source_decision=request.source_decision,
        governance_context=request.governance_context or {},
        evidence=request.evidence or {},
        status=request.status,
        ao_ref=request.ao_ref,
        aee_ref=request.aee_ref,
        ect_ref=request.ect_ref,
        decision_record_ref=request.decision_record_ref,
        decision_record_digest=request.decision_record_digest,
        aee_conditions=aee_conditions
    )


def _validate_intent_authority_match(intent: RuntimeIntent, authority: ExecutionAuthority) -> None:
    """
    Validate that the intent matches the authority.

    This is a critical security check: caller-supplied JSON must not be
    treated as authentic authority merely because it parses.
    """
    # Check exact match on core fields
    if intent.principal != authority.principal:
        raise HTTPException(
            status_code=403,
            detail=f"Intent principal '{intent.principal}' does not match authority principal '{authority.principal}'"
        )

    if intent.action != authority.action:
        raise HTTPException(
            status_code=403,
            detail=f"Intent action '{intent.action}' does not match authority action '{authority.action}'"
        )

    if intent.target != authority.target:
        raise HTTPException(
            status_code=403,
            detail=f"Intent target '{intent.target}' does not match authority target '{authority.target}'"
        )

    if intent.environment != authority.environment:
        raise HTTPException(
            status_code=403,
            detail=f"Intent environment '{intent.environment}' does not match authority environment '{authority.environment}'"
        )

    # Check parameters (exact match for simplicity in v0.1)
    # In production, this may use parameter constraints instead
    if intent.parameters != authority.parameters:
        raise HTTPException(
            status_code=409,
            detail="Intent parameters do not match authority parameters"
        )


def _validate_authority_trust(authority_request: ExecutionAuthorityRequest) -> None:
    """
    Verify the Ed25519 signature over canonical authority fields.

    EGA_AUTHORITY_PUBLIC_KEYS_JSON maps authority IDs to base64-encoded raw
    32-byte Ed25519 public keys. The signature is base64-encoded and covers
    every authority request field except the signature itself.
    """
    import base64
    import binascii
    import json

    raw_keys = os.getenv("EGA_AUTHORITY_PUBLIC_KEYS_JSON", "")
    if raw_keys:
        try:
            keys = json.loads(raw_keys)
        except (TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=503, detail="Authority verification is misconfigured")
        if not isinstance(keys, dict):
            raise HTTPException(status_code=503, detail="Authority verification is misconfigured")

        encoded_key = keys.get(authority_request.authority_id)
        if not isinstance(encoded_key, str) or not authority_request.signature:
            raise HTTPException(status_code=403, detail="Authority signature is missing or untrusted")

        # Signed authorities must be time-bounded and intended for this service.
        issued_at = authority_request.issued_at
        expires_at = authority_request.expires_at
        if issued_at is None or expires_at is None or not authority_request.audience:
            raise HTTPException(status_code=403, detail="Authority validity fields are missing")
        if issued_at.tzinfo is None or issued_at.utcoffset() is None or expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise HTTPException(status_code=403, detail="Authority timestamps must include a timezone")
        now = datetime.now(timezone.utc)
        issued_utc = issued_at.astimezone(timezone.utc)
        expires_utc = expires_at.astimezone(timezone.utc)
        if authority_request.audience != SERVICE_AUDIENCE:
            raise HTTPException(status_code=403, detail="Authority audience does not match this service")
        if issued_utc.timestamp() > now.timestamp() + AUTHORITY_CLOCK_SKEW_SECONDS:
            raise HTTPException(status_code=403, detail="Authority is not yet valid")
        if expires_utc <= now or expires_utc <= issued_utc:
            raise HTTPException(status_code=403, detail="Authority has expired or has an invalid validity interval")
        if (expires_utc - issued_utc).total_seconds() > MAX_AUTHORITY_TTL_SECONDS:
            raise HTTPException(status_code=403, detail="Authority validity interval exceeds configured maximum")

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            raise HTTPException(status_code=503, detail="Ed25519 verification dependency is unavailable")

        try:
            public_key_bytes = base64.b64decode(encoded_key, validate=True)
            signature_bytes = base64.b64decode(authority_request.signature, validate=True)
            payload = authority_request.model_dump(exclude={"signature"}, mode="json")
            canonical_payload = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if len(public_key_bytes) != 32:
                raise ValueError("invalid Ed25519 public key length")
            Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
                signature_bytes, canonical_payload
            )
        except (ValueError, binascii.Error, InvalidSignature):
            raise HTTPException(status_code=403, detail="Authority signature verification failed")
        return

    if not ALLOW_UNVERIFIED_AUTHORITY:
        raise HTTPException(
            status_code=503,
            detail="Authority verification keys are not configured; evaluation is disabled"
        )

    # Explicitly unsafe model/demo mode only.
    if TRUSTED_AUTHORITY_IDS and authority_request.authority_id not in TRUSTED_AUTHORITY_IDS:
        raise HTTPException(status_code=403, detail="Authority ID is not in the configured test whitelist")
    if not TRUSTED_AUTHORITY_IDS and FAIL_CLOSED_ON_UNKNOWN_AUTHORITY:
        raise HTTPException(status_code=403, detail="No authority IDs configured for unsafe test mode")

    import warnings
    warnings.warn(
        "EGA_ALLOW_UNVERIFIED_AUTHORITY=true: accepting caller-supplied, "
        "cryptographically unverified authority. TEST/DEMO ONLY.",
        RuntimeWarning,
        stacklevel=2,
    )


def _convert_evidence_envelopes(
    envelope_requests: list[EvidenceEnvelopeRequest],
) -> Dict[str, EvidenceItem]:
    """
    Convert Observer v1 evidence envelopes to EGA EvidenceItem dict.

    Uses the existing observer_v1_envelope_to_evidence() adapter which:
    - Validates envelope integrity
    - Validates evidence_id derivation
    - Computes freshness from observed_at
    - Performs all security checks

    Raises HTTPException if conversion fails.
    """
    evidence_dict: Dict[str, EvidenceItem] = {}

    for envelope_request in envelope_requests:
        try:
            # Convert Pydantic model to dict
            envelope_dict = envelope_request.model_dump()

            # Use existing adapter for conversion
            evidence_item = observer_v1_envelope_to_evidence(
                envelope_dict,
                evaluation_status="USED",
                role="commit_condition",
                max_age_seconds=MAX_CONTEXT_AGE_SECONDS,
            )

            # Check for freshness before adding
            if evidence_item.freshness == "STALE":
                raise HTTPException(
                    status_code=400,
                    detail=f"Evidence {evidence_item.evidence_ref} is stale (older than {MAX_CONTEXT_AGE_SECONDS} seconds)"
                )

            evidence_dict[evidence_item.evidence_ref] = evidence_item

        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Evidence envelope validation failed: {str(e)}"
            )

    return evidence_dict


@app.post("/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
    """
    Evaluate a RuntimeIntent against an ExecutionAuthority.

    This endpoint:
    - Validates the intent and authority structures
    - Checks that intent matches authority (prevents forged authority)
    - Uses existing EGA core functions: prepare(), final_authority_check(), commit()
    - Returns COMMIT/BLOCK decision

    This does NOT issue authority. Authority must be pre-issued by a trusted
    governance system. This endpoint only evaluates an existing authority
    against a specific runtime intent.
    """
    try:
        # Convert Pydantic models to EGA models
        intent = _convert_intent(request.intent)
        authority = _convert_authority(request.authority)

        # Security check 1: validate authority trust (whitelist)
        _validate_authority_trust(request.authority)

        # Security check 2: validate intent-authority match
        _validate_intent_authority_match(intent, authority)

        # Security check 3: context freshness (wall-clock check, separate from epoch semantics)
        current_system_time = int(time.time())
        context_age = current_system_time - request.context_epoch
        if context_age > MAX_CONTEXT_AGE_SECONDS:
            raise HTTPException(
                status_code=400,
                detail=f"Context epoch is stale (age: {context_age}s, max: {MAX_CONTEXT_AGE_SECONDS}s)"
            )
        if context_age < -MAX_CONTEXT_AGE_SECONDS:
            raise HTTPException(
                status_code=400,
                detail=f"Context epoch is in the future (age: {context_age}s, max skew: {MAX_CONTEXT_AGE_SECONDS}s)"
            )

        # Use existing EGA boundary functions
        prepared = prepare(authority, request.context_epoch)

        # Evidence handling: convert Observer v1 envelopes to EvidenceItem
        current_evidence = None
        if prepared.authority.aee_conditions:
            # AEE conditions are present - evidence is required
            if not request.intent.evidence_envelopes:
                raise HTTPException(
                    status_code=400,
                    detail="AEE conditions present in authority but no evidence envelopes provided in intent"
                )

            # Convert Observer v1 envelopes to EvidenceItem dict
            current_evidence = _convert_evidence_envelopes(request.intent.evidence_envelopes)
        elif request.intent.evidence_envelopes:
            # No AEE conditions but evidence provided - convert but don't use
            current_evidence = None

        # Final authority check: use prepared.context_epoch for epoch/version semantics
        # The wall-clock freshness check was done separately above
        reason = final_authority_check(
            prepared,
            prepared.context_epoch,  # Use prepared epoch for epoch/version semantics
            current_authority=None,  # Not checking for authority changes in v0.1.2
            current_evidence=current_evidence
        )

        # Commit decision: use prepared.context_epoch for epoch/version semantics
        result = commit(
            prepared,
            prepared.context_epoch,  # Use prepared epoch for epoch/version semantics
            current_evidence=current_evidence
        )

        return EvaluateResponse(
            decision=result["decision"],
            reason=result["reason"],
            applied=result["applied"],
            effect=result["effect"]
        )

    except HTTPException:
        # Re-raise HTTP exceptions with their status codes
        raise
    except ValueError as e:
        # Don't leak internal error details in production
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        # Log the error in production, don't leak details to client
        # TODO: Add proper logging
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.3"}


def run_server(host: str = None, port: int = None):
    """Run the HTTP service."""
    if host is None:
        host = DEFAULT_HOST
    if port is None:
        port = DEFAULT_PORT
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run_server(host, port)
