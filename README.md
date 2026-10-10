# EGA — Execution Governance Authority

EGA is a reference architecture for the authorization-to-execution-authority step: it turns Runtime AI Governance output into explicit, bounded execution authority that a downstream execution boundary (such as EABC) can consume. The repository includes a minimal executable model of this step. It is not an implementation of EABC and not a production system.

```
Runtime AI Governance
        │
        │ runtime intent + governance context + evidence
        ▼
EGA — Execution Governance Authority
        │
        │ explicit execution authority
        ▼
EABC — Execution Authority Boundary Contract
        │
        │ current execution conditions
        ▼
Enforcement Boundary
        │
        ▼
EFFECT
```

## Role

EGA is an **authorization-to-execution-authority bridge**.

It accepts runtime intent and relevant governance context, normalizes heterogeneous upstream outputs, evaluates the intent against applicable authorization scope, and produces explicit execution authority for downstream enforcement.

EGA is **authorization-complete but execution-blind**.

It does not commit effects or determine whether an authorized action may become an effect under current execution conditions.

## Evidence boundary

EGA may receive runtime evidence from an upstream Observer or equivalent evidence source through a provider-neutral evidence envelope.

The evidence contract carries evidence identity, subject or target, state or value, observation time, temporal basis, provenance, uncertainty, source confidence where provided, schema version, and an integrity reference.

The Observer reports evidence. It does not assign materiality, create execution authority, or promote evidence into a commit condition.

EGA determines which evidence is materially relevant to authorization and, where required, explicitly projects selected evidence properties into execution-boundary conditions.

An evidence change does not by itself invalidate an execution condition. The condition is evaluated against the current evidence at the execution boundary.

## What EGA does

- accepts Runtime AI Governance output or equivalent upstream authority input;
- normalizes runtime intent and governance context;
- evaluates intent against applicable authorization scope;
- derives bounded execution authority;
- preserves authorization lineage and evidence;
- hands explicit execution authority to a downstream execution boundary.

## What EGA does not do

EGA does not:

- execute actions;
- commit effects;
- determine the actual state transition;
- replace Runtime AI Governance;
- replace EABC;
- determine physical or logical execution safety;
- choose software versus hardware enforcement;
- guarantee that an authorized action will execute.

## EGA is optional to EABC

EABC is implementation-neutral and does not require EGA.

```
Authority Source → EABC → Enforcement Boundary → EFFECT
```

EGA provides one concrete architecture for the upstream authorization-to-execution-authority transition:

```
Runtime AI Governance → EGA → EABC → Enforcement Boundary → EFFECT
```

## Executable model

The repository contains a minimal deterministic Python model of the EGA step.

```bash
python -m pip install -e ".[test,service]"
pytest -q
```

The implementation does not execute external actions. It includes a semantic PREPARE / FINAL_AUTHORITY_CHECK / COMMIT seam and emits `ExecutionAttestation` evidence for the resulting commit or block decision.

## Examples

- [Minimal EGA → EABC flow](examples/minimal/README.md)
- [Human boundary / substituted execution path](examples/jozsef-human-boundary/README.md)
- [Observer → EGA evidence handoff](examples/jozsef-observer-handoff/golden-case.md)

The second example models a provider-neutral runtime-control failure: a human restriction permits only execution path A, path A becomes unavailable, and a technically available substitute path B must not acquire execution authority merely because the system can execute it.

## Repository status

The reference architecture and the RAIG/Observer → EGA interoperability seams are defined. The executable model includes a minimal contract for runtime intent, external authorization scope, fail-closed evaluation, execution-authority issuance, and a prepare/final-check/commit seam.

See:

- [Reference Architecture](docs/reference-architecture.md)
- [RAIG → EGA Interface](docs/raig-interface.md)
- [Execution Authority](docs/execution-authority.md)
- [Minimal Example](examples/minimal/README.md)

## Related work

- EABC: https://github.com/omwei-org/omwei-eabc

## HTTP service authority verification

The optional HTTP service is a reference implementation, not a production deployment. By default, `POST /v1/evaluate` fails closed unless an Ed25519 public key is provisioned for the submitted `authority_id`.

Configure `EGA_AUTHORITY_PUBLIC_KEYS_JSON` as a JSON object mapping authority IDs to base64-encoded raw 32-byte Ed25519 public keys. The request's `authority.signature` must be base64-encoded Ed25519 over the canonical UTF-8 JSON serialization of the validated authority model excluding `signature`, using sorted keys, compact separators (`,` and `:`), and `ensure_ascii=False`. The signer must include `nonce`, `issued_at`, `expires_at`, and `audience` in the signed payload; each authority nonce must be unique for that authority ID and at least 16 characters long. timestamps must include a timezone, the audience must match `EGA_SERVICE_AUDIENCE`, and the validity interval must not exceed `EGA_MAX_AUTHORITY_TTL_SECONDS`. Because the server verifies the normalized Pydantic model rather than raw request bytes, the signer and verifier must use the same schema and canonicalization.

Example key-map shape (replace the placeholder with a real public key):
```json
{"authority-id": "BASE64_RAW_ED25519_PUBLIC_KEY"}
```

Do not enable `EGA_ALLOW_UNVERIFIED_AUTHORITY=true` outside isolated tests/demos. That switch bypasses signature verification when no key map is configured. The current service enforces signed authority expiry and audience, and atomically records consumed nonces in a local SQLite ledger. The ledger only protects service instances sharing the same database file; multi-host deployments need a shared strongly consistent store. Revocation, key rotation, and HTTP client authentication remain unimplemented. A provider interface is present, but no live ComOS-backed provider is bundled. Signature verification authenticates the signed authority payload against the provisioned key; it does not by itself establish that the authority is current or that the execution boundary enforces the resulting decision.


Replay protection configuration: set `EGA_REPLAY_DB_PATH` to a persistent writable SQLite database file. If the ledger is unavailable, the service fails closed with HTTP 503. Reusing a consumed `(authority_id, nonce)` returns HTTP 409. Do not use this local SQLite ledger as a distributed replay defense across hosts or containers without a shared filesystem and appropriate SQLite locking guarantees.

## Trusted context version provider

The HTTP service deliberately has no default context provider. `context_epoch` is an opaque version identifier for the caller's context snapshot, not a timestamp. The service calls the configured provider before preparation and again immediately before the final authority check. If the caller's version differs from the trusted current version, or the provider is missing, unavailable, or returns an invalid version, the service blocks or fails closed.

An embedding application must install `ega.service.CONTEXT_VERSION_PROVIDER` at startup. The provider must query a trusted source of current state and derive the relevant scope from the request's intent; it must not simply return the caller-supplied `context_epoch`. For example:

```python
from ega import service

def current_context_version(request: service.EvaluateRequest) -> int:
    # Resolve the relevant tenant/resource from request.intent, then query
    # a trusted, authoritative version source. Do not trust request.context_epoch.
    return trusted_state_store.version_for(
        principal=request.intent.principal,
        action=request.intent.action,
        target=request.intent.target,
        environment=request.intent.environment,
    )

service.CONTEXT_VERSION_PROVIDER = current_context_version
```

The example is an integration contract, not a bundled ComOS adapter. No live ComOS context-version source is implemented in this repository. A provider re-read narrows the stale-context window but does not make the decision atomic with a later external effect. The actual execution boundary must independently enforce current context and authority at the point of effect; the EGA service returns a decision and does not execute the effect.
