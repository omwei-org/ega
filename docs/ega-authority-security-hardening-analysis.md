# EGA Authority Security Hardening - Pre-Implementation Analysis

**Date**: 2026-10-10
**Purpose**: Analyze current authority model and design security hardening
**Status**: PRE-IMPLEMENTATION ANALYSIS

> **Historical snapshot — not current implementation documentation.** This document records the pre-implementation state observed during the 2026-10-10 analysis. The target branch now contains authority-signature verification, authority time-window and audience checks, fail-closed configuration, a trusted context-version provider, authority-status rechecks, and a SQLite nonce replay ledger in `src/ega/service.py`. For the current contract and configuration, the service source and its tests are authoritative. The proposed standalone `crypto.py` and in-memory `nonce_tracker.py` helpers were intentionally excluded from this PR because they duplicated or diverged from the existing service implementation.

---

## 1. HTTP Test Boundary Verification

### Current Implementation

**File**: `tests/test_comos_ega_service_integration.py`

**Test Architecture**:
```python
@pytest.fixture(scope="module")
def ega_service():
    """Start EGA service for testing."""
    # Start service in subprocess
    proc = subprocess.Popen(
        ["python", "-m", "ega.service"],
        env={**subprocess.os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for service to start
    time.sleep(2)

    yield {
        "process": proc,
        "url": "http://127.0.0.1:8000"
    }

    # Cleanup: shutdown service
    proc.terminate()
```

**Finding**: ✅ **TESTS USE REAL LOCAL HTTP SERVER**

**Evidence**:
- Tests start a real EGA HTTP service in a subprocess (line 174-179)
- Service runs on `127.0.0.1:8000` (line 168-169)
- Tests make actual HTTP requests using `requests` library (line 66 in client)
- Request/response handling goes through actual HTTP boundary
- Service is terminated after tests (line 190-194)

**Test Client**:
```python
class EGAServiceTestClient:
    def evaluate(self, authority, intent, context_epoch, evidence_envelopes=None):
        url = f"{self.base_url}/v1/evaluate"
        payload = {"authority": authority, "intent": intent, "context_epoch": context_epoch}
        if evidence_envelopes:
            payload["intent"]["evidence_envelopes"] = evidence_envelopes
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
```

**Verification**:
- ✅ No internal function calls bypass HTTP
- ✅ No mocking of service
- ✅ Rejection and error responses tested through HTTP boundary (HTTP 403, 409, 400, 422)
- ✅ Test names are accurate: "service-level" indicates actual HTTP testing

**Conclusion**: The HTTP integration tests are genuine service-level tests against a real local HTTP server. The model-level harness (`test_comos_ega_harness.py`) is separate and documented as model-level only.

---

## 2. Current Authority Model Inspection

### ExecutionAuthority Model

**File**: `src/ega/models.py` (lines 73-90)

```python
@dataclass(frozen=True)
class ExecutionAuthority:
    authority_id: str
    principal: str
    action: str
    target: str
    parameters: dict[str, Any]
    environment: str
    source_decision: str
    governance_context: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "VALID"
    ao_ref: str | None = None
    aee_ref: str | None = None
    ect_ref: str | None = None
    decision_record_ref: str | None = None
    decision_record_digest: str | None = None
    aee_conditions: tuple[AEECondition, ...] = field(default_factory=tuple)
```

**Missing Fields**:
- ❌ `signature` (cryptographic signature)
- ❌ `nonce` (replay protection)
- ❌ `expires_at` (validity interval)
- ❌ `not_before` (validity interval)
- ❌ `audience` (context binding)
- ❌ `issued_at` (timestamp)

### Current Data Flow

**Authority Issuance** (`src/ega/authority.py`):
```python
def issue_authority(intent: RuntimeIntent, scope: AuthorizationScope, decision_record: DecisionRecord) -> ExecutionAuthority:
    # Creates authority without cryptographic signing
    # No signature generation
    # No nonce generation
    # No expiry time generation
    return ExecutionAuthority(...)
```

**Authority Verification** (`src/ega/service.py`):
```python
def _validate_authority_trust(authority: ExecutionAuthority) -> None:
    # Uses whitelist-based trust, not signature verification
    if not TRUSTED_AUTHORITY_IDS:
        if FAIL_CLOSED_ON_UNKNOWN_AUTHORITY:
            raise HTTPException(status_code=403, ...)
    if authority.authority_id not in TRUSTED_AUTHORITY_IDS:
        raise HTTPException(status_code=403, ...)
```

**Intent-Authority Match** (`src/ega/service.py`):
```python
def _validate_intent_authority_match(intent: RuntimeIntent, authority: ExecutionAuthority) -> None:
    # Exact match on core fields
    if intent.principal != authority.principal:
        raise HTTPException(status_code=403, ...)
    if intent.action != authority.action:
        raise HTTPException(status_code=403, ...)
    if intent.target != authority.target:
        raise HTTPException(status_code=403, ...)
    if intent.environment != authority.environment:
        raise HTTPException(status_code=403, ...)
    if intent.parameters != authority.parameters:
        raise HTTPException(status_code=409, ...)
```

**Current Trust Boundaries**:
1. **Transport**: TLS (assumed, not enforced by service)
2. **Trust Whitelist**: `EGA_TRUSTED_AUTHORITY_IDS` environment variable
3. **Fail-Closed Mode**: `EGA_FAIL_CLOSED=true` rejects unknown authorities
4. **Intent-Authority Match**: Exact match on all fields
5. **Wall-Clock Freshness**: `MAX_CONTEXT_AGE_SECONDS` limits context staleness

**No Cryptographic Boundaries**:
- No signature verification
- No authority digest verification
- No nonce-based replay protection
- No expiry-based validity enforcement

---

## 3. Security Hardening Design

### 3.1 Cryptographic Authenticity

**Design**: Add Ed25519 signature to ExecutionAuthority

**Fields to Add**:
```python
@dataclass(frozen=True)
class ExecutionAuthority:
    # ... existing fields ...
    signature: str  # Ed25519 signature over canonical authority
    public_key_id: str  # Reference to trusted public key
    issued_at: str  # ISO 8601 timestamp
```

**Trusted Keys Configuration**:
- `EGA_TRUSTED_PUBLIC_KEYS`: Environment variable with JSON mapping of public_key_id → Ed25519 public key (base64)
- Service loads trusted keys at startup
- Service rejects authorities with unknown or untrusted public_key_id

**Signature Verification**:
- Canonicalize authority (excluding signature field)
- Verify Ed25519 signature using trusted public key
- Reject invalid signatures with HTTP 403

### 3.2 Intent Binding

**Design**: Bind signature to canonical intent representation

**Canonicalization Rules**:
- JSON serialization with sorted keys
- Exclude signature field from canonical form
- Convert numbers to string to avoid precision issues
- Use deterministic encoding (UTF-8)
- Compute SHA-256 hash of canonical form as signing target

**Implementation**:
```python
def _canonicalize_authority(authority: ExecutionAuthority) -> bytes:
    """Canonicalize authority for signing."""
    authority_dict = asdict(authority)
    authority_dict.pop("signature", None)  # Exclude signature
    authority_dict.pop("public_key_id", None)  # Exclude public key reference
    # Sort keys for deterministic order
    sorted_dict = dict(sorted(authority_dict.items()))
    # Convert to JSON with no extra whitespace
    canonical_json = json.dumps(sorted_dict, sort_keys=True, separators=(',', ':'))
    return canonical_json.encode('utf-8')
```

### 3.3 Validity Interval

**Design**: Add `not_before` and `expires_at` fields

**Fields to Add**:
```python
@dataclass(frozen=True)
class ExecutionAuthority:
    # ... existing fields ...
    not_before: str  # ISO 8601 timestamp (not valid before this time)
    expires_at: str  # ISO 8601 timestamp (not valid after this time)
```

**Validation**:
- Reject if `current_time < not_before` (HTTP 403)
- Reject if `current_time > expires_at` (HTTP 403)
- Both checks are fail-closed

**Revocation**: Not implemented in Phase 1 (separate from expiry)

### 3.4 Context Binding

**Design**: Add `audience` field

**Field to Add**:
```python
@dataclass(frozen=True)
class ExecutionAuthority:
    # ... existing fields ...
    audience: str  # Intended audience (e.g., "comos-hub", "comos-node")
```

**Validation**:
- Reject if `audience` does not match configured service audience
- Service audience configured via `EGA_AUDIENCE` environment variable
- Fail-closed if mismatch

### 3.5 Replay Protection

**Design**: Add `nonce` field with durable tracking

**Field to Add**:
```python
@dataclass(frozen=True)
class ExecutionAuthority:
    # ... existing fields ...
    nonce: str  # Unique identifier for replay protection
```

**Storage**:
- In-memory set for testing (simple)
- Redis for production (not implemented in Phase 1)
- Key: `authority_id:nonce`

**Atomic Operation**:
```python
async def consume_nonce(authority_id: str, nonce: str) -> bool:
    """Atomically consume nonce if not already used."""
    key = f"nonce:{authority_id}:{nonce}"
    # Use Redis SETNX for atomicity
    return redis.set(key, "1", nx=True, ex=3600)  # 1 hour expiry
```

**For Testing**: Use in-memory set with threading.Lock for atomicity

### 3.6 Fail-Closed Behavior

**Rejection Cases**:
- Missing signature → HTTP 403
- Invalid signature → HTTP 403
- Unknown public_key_id → HTTP 403
- Expired authority → HTTP 403
- Not-yet-valid authority → HTTP 403
- Audience mismatch → HTTP 403
- Replayed nonce → HTTP 403
- Malformed authority → HTTP 400
- Verification service failure → HTTP 500
- Missing required fields → HTTP 422

**All Rejections**: No protected effects authorized

---

## 4. Concurrency and Atomicity

### Replay Protection Concurrency

**Challenge**: Two concurrent requests attempt to use same authority

**Solution**: Atomic nonce consumption

**Using Redis (Production)**:
```python
async def consume_nonce(authority_id: str, nonce: str) -> bool:
    """Atomically consume nonce using Redis SETNX."""
    key = f"nonce:{authority_id}:{nonce}"
    # SETNX returns True only if key does not exist
    return redis.set(key, "1", nx=True, ex=3600)
```

**Using In-Memory Set (Testing)**:
```python
import threading

class NonceTracker:
    def __init__(self):
        self.consumed_nonces = set()
        self.lock = threading.Lock()

    def consume(self, authority_id: str, nonce: str) -> bool:
        with self.lock:
            key = f"{authority_id}:{nonce}"
            if key in self.consumed_nonces:
                return False
            self.consumed_nonces.add(key)
            return True
```

**Consumption Point**: After signature verification, before commit decision

**Crash/Retry Semantics**:
- If service crashes after nonce consumption but before response, caller may retry
- Retries will fail (nonce already consumed)
- This is acceptable: better to over-reject than over-authorize
- Caller must obtain new authority for retry

**Exact-Once Execution**: NOT CLAIMED - nonce consumption prevents replay but does not guarantee exactly-once execution in presence of service crashes or network failures.

---

## 5. Payload Canonicalization

### Canonicalization Rules

**Python Implementation**:
```python
def _canonicalize_authority(authority: ExecutionAuthority) -> bytes:
    """Canonicalize authority for signing."""
    # Convert to dict
    authority_dict = asdict(authority)

    # Exclude fields that are not part of signature
    authority_dict.pop("signature", None)
    authority_dict.pop("public_key_id", None)

    # Sort keys for deterministic order
    sorted_dict = dict(sorted(authority_dict.items()))

    # Convert to JSON with compact encoding
    canonical_json = json.dumps(sorted_dict, sort_keys=True, separators=(',', ':'))

    return canonical_json.encode('utf-8')
```

**Rules**:
- Keys sorted alphabetically
- No extra whitespace
- UTF-8 encoding
- Numbers as-is (no scientific notation)
- Null values preserved
- Booleans as true/false
- Lists and dicts as-is (nested sorting for dicts)

**Mutation Detection**:
- Re-canonicalize at commit boundary
- Compare with signed canonical form
- Reject if mismatch (HTTP 409)

---

## 6. Implementation Plan

### Phase 1: Model Changes

1. Add fields to `ExecutionAuthority`:
   - `signature: str`
   - `public_key_id: str`
   - `issued_at: str`
   - `not_before: str`
   - `expires_at: str`
   - `audience: str`
   - `nonce: str`

2. Add `_canonicalize_authority()` function

3. Add `_verify_signature()` function

4. Add `_validate_validity_interval()` function

5. Add `_validate_audience()` function

6. Add `NonceTracker` class for testing

### Phase 2: Service Changes

1. Update `ExecutionAuthorityRequest` Pydantic model to include new fields
2. Update `_convert_authority()` to handle new fields
3. Update `_validate_authority_trust()` to use public_key_id instead of authority_id whitelist
4. Add signature verification in evaluate endpoint
5. Add validity interval checks
6. Add audience check
7. Add nonce consumption check
8. Update error messages for new rejection reasons

### Phase 3: Authority Issuance Changes

1. Update `issue_authority()` to:
   - Generate nonce
   - Add issued_at timestamp
   - Add not_before (current time)
   - Add expires_at (configurable TTL)
   - Add audience (from config)
   - Generate signature using configured private key
   - Add public_key_id reference

2. Add key configuration:
   - `EGA_PRIVATE_KEY`: Ed25519 private key (base64)
   - `EGA_PUBLIC_KEY_ID`: Public key identifier

### Phase 4: Test Changes

1. Add test key generation utilities
2. Add tests for:
   - Valid signed authority
   - Invalid signature
   - Expired authority
   - Not-yet-valid authority
   - Audience mismatch
   - Replayed nonce
   - Concurrent replay attempts
   - Payload mutation after authorization
   - Malformed authority
   - Service unavailable
   - Missing required fields
   - Unknown public key
   - Invalid signature format

---

## 7. Migration and Configuration Requirements

### New Environment Variables

```
EGA_PRIVATE_KEY=<base64-encoded Ed25519 private key>
EGA_PUBLIC_KEY_ID=<public key identifier>
EGA_TRUSTED_PUBLIC_KEYS=<JSON mapping of public_key_id -> base64 public key>
EGA_AUDIENCE=<intended audience (e.g., "comos-hub")>
EGA_AUTHORITY_TTL_SECONDS=<default validity interval, default 3600>
```

### Breaking Changes

**Existing Authority Format**: Incompatible with new format

**Migration Path**:
- Old authorities without signature will be rejected
- Consumers must upgrade to new authority format
- Provide migration period with dual-mode support (optional, not in Phase 1)

### Compatibility Implications

**Existing Tests**:
- Tests using unsigned authorities will fail
- Service tests will need test keys
- Model-level harness will need signature verification
- Observer integration tests unaffected (do not use authority)

**Existing Consumers**:
- Must obtain signed authorities from governance system
- Must include nonce in each request
- Must handle new rejection reasons (expired, replay, etc.)

---

## 8. Remaining Limitations After Phase 1

Even after Phase 1 implementation, the following will remain absent:

1. **Revocation**: No revocation mechanism (separate from expiry)
2. **Production Replay Storage**: In-memory set only (not suitable for production)
3. **Key Rotation**: No mechanism to rotate keys without downtime
4. **Audit Trail**: No audit trail of authority usage
5. **Governance System Lookup**: No integration with governance system

These are documented in the implementation as Phase 2+ items.

---

**End of Analysis**
