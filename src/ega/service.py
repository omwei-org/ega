"""
EGA HTTP Service for ComOS Integration

This service provides an HTTP API for evaluating RuntimeIntent against
ExecutionAuthority using the existing EGA core functions.

Architecture:
- POST /v1/evaluate endpoint
- Uses existing EGA functions: prepare(), final_authority_check(), commit()
- Distinguishes authority issuance from evaluation
- Rejects malformed/invalid authority

Security features (v0.1.2):
- Trusted authority whitelist (fail-closed by default)
- AEE conditions require Observer v1 evidence or block
- Evidence converted using existing observer_v1_envelope_to_evidence()
- AEE conditions evaluated against converted evidence
- Independent context epoch from system time (staleness detection)
- Binds to 127.0.0.1 by default
- Generic error messages (no internal details leaked)
- HTTP authentication not implemented (requires network security layer)

Security limitations (v0.1.2 - ARCHITECTURAL):
- No cryptographic signature verification (not in EGA models)
- No authority expiry/revocation (not in EGA models)
- No replay protection (not in EGA models)
- Authority retrieval from trusted governance system not implemented
- These require EGA core model changes, not service-layer changes

Configuration:
- EGA_HOST: Bind address (default: 127.0.0.1)
- EGA_PORT: Port (default: 8000)
- EGA_TRUSTED_AUTHORITY_IDS: Comma-separated list of trusted authority IDs (default: empty)
- EGA_FAIL_CLOSED: If true, reject authorities not in whitelist (default: true)
- EGA_MAX_CONTEXT_AGE_SECONDS: Max allowed age for context epoch (default: 300)

Usage:
  # Production mode (fail-closed, requires whitelist)
  EGA_TRUSTED_AUTHORITY_IDS=auth-001,auth-002 python3 -m ega.service

  # Test mode (fail-open, for testing only)
  EGA_FAIL_CLOSED=false python3 -m ega.service
"""

from typing import Any, Dict, Optional, Set
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
import uvicorn
import os
import time

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
MAX_CONTEXT_AGE_SECONDS = int(os.getenv("EGA_MAX_CONTEXT_AGE_SECONDS", "300"))  # 5 minutes default


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
    version="0.1.0"
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


def _validate_authority_trust(authority: ExecutionAuthority) -> None:
    """
    Validate that the authority is from a trusted source.

    This uses a whitelist of trusted authority IDs. If the whitelist is empty
    and FAIL_CLOSED_ON_UNKNOWN_AUTHORITY is true, all authorities are rejected.
    If the whitelist is empty and FAIL_CLOSED_ON_UNKNOWN_AUTHORITY is false,
    the service operates in unsafe mode (for testing only).

    This is a minimal trust mechanism for v0.1.2. Production should use
    cryptographic signature verification or lookup from a trusted governance system.

    ARCHITECTURAL LIMITATION: EGA models do not support signature verification.
    This whitelist-based approach is a fallback until signature fields are added
    to ExecutionAuthority model.
    """
    if not TRUSTED_AUTHORITY_IDS:
        if FAIL_CLOSED_ON_UNKNOWN_AUTHORITY:
            raise HTTPException(
                status_code=403,
                detail=f"Authority '{authority.authority_id}' not in trusted whitelist and fail-closed mode is enabled. "
                        f"Set EGA_TRUSTED_AUTHORITY_IDS or set EGA_FAIL_CLOSED=false for testing."
            )
        # Fail-open mode for testing - log warning but allow
        import warnings
        warnings.warn(
            f"EGA_TRUSTED_AUTHORITY_IDS is empty and EGA_FAIL_CLOSED=false. "
            f"Accepting authority '{authority.authority_id}' in unsafe mode. "
            f"This is suitable for testing only."
        )
        return

    if authority.authority_id not in TRUSTED_AUTHORITY_IDS:
        raise HTTPException(
            status_code=403,
            detail=f"Authority '{authority.authority_id}' not in trusted whitelist"
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
        _validate_authority_trust(authority)

        # Security check 2: validate intent-authority match
        _validate_intent_authority_match(intent, authority)

        # Security check 3: context freshness (use system time for current_epoch)
        current_epoch = int(time.time())
        context_age = current_epoch - request.context_epoch
        if context_age > MAX_CONTEXT_AGE_SECONDS:
            raise HTTPException(
                status_code=400,
                detail=f"Context epoch is stale (age: {context_age}s, max: {MAX_CONTEXT_AGE_SECONDS}s)"
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

        # Final authority check
        reason = final_authority_check(
            prepared,
            current_epoch,  # Use system time for current_epoch
            current_authority=None,  # Not checking for authority changes in v0.1.2
            current_evidence=current_evidence
        )

        # Commit decision
        result = commit(
            prepared,
            current_epoch,  # Use system time for current_epoch
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
    return {"status": "healthy", "version": "0.1.0"}


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
