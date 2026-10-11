# ComOS integration handoff readiness (working note)

Status: **EGA-side HTTP contract partially verified; end-to-end ComOS integration not yet proven.**
Scope: this note separates verified EGA behavior from the remaining ComOS implementation and acceptance work. It does not claim that ComOS has been modified.

## 1. Verified EGA interface

The current `src/ega/service.py` on `integration/comos-http-gate-v01` exposes `POST /v1/evaluate` with:

- request: `{ intent, authority, context_epoch }`
- response model: `{ decision, reason, applied, effect }`
- expected permit: `decision = COMMIT`, `applied = true`, non-empty `reason`, and `effect = NONE | NOT_EXECUTED`
- HTTP errors, invalid response shapes, non-COMMIT decisions, and transport failures must be treated as denial by the caller.

The service verifies the signed authority when configured with trusted keys, checks authority/intent equality, checks trusted context version, can check authority status, and claims the authority nonce in its replay ledger. Production readiness still depends on deployment-supplied trusted providers and appropriate transport/authentication controls.

## 2. Important schema boundary

The current `RuntimeIntentRequest.parameters` schema is specific: `items: [{ product_id, quantity }]` plus optional `expected_total_coms`. `_validate_intent_authority_match` compares the converted intent parameters to the authority parameters exactly.

Therefore, an integration must **not** assume that freezing a larger ComOS payload proves all of it was authorized. The ComOS adapter must define, field by field, which values can affect the protected `order_create` effect and ensure that every such value is represented in the EGA intent and authority scope, or is separately bound by a verified invariant. Do not silently discard execution-relevant fields such as trusted buyer/payer, vendor, price/total, currency, or destination if those fields are used by the actual handler.

The TypeScript helper's `buildIntent` callback is caller-defined. Its snapshot/freeze behavior only ensures the callback and execution receive the same local snapshot; it does not prove that `buildIntent` included every execution-relevant field, nor does it bind the remote node's later execution.

## 3. Required ComOS integration point

The insertion point must be confirmed against the current served `order_create` path, not inferred from older names such as `routeToolCall` or `beginPerActCharge`.

The intended sequence is:

1. Authenticate caller and derive trusted identity/scope.
2. Resolve the vendor and build the final trusted order/ACT payload, including hub-derived values.
3. Derive EGA intent from that exact payload and the pre-existing authority; obtain `context_epoch` from trusted current state.
4. Call EGA before charging, queue insertion, order creation, or another protected effect.
5. On anything other than a valid COMMIT, stop without enqueuing ACT or creating the protected order.
6. On COMMIT, enqueue only the payload covered by the authorization. Any execution-relevant change requires reauthorization.
7. At the node execution boundary, verify integrity/binding of the ACT payload actually executed. A hub-side decision alone does not close a payload-substitution gap in node transport.

## 4. Acceptance tests ComOS must demonstrate

- **COMMIT:** the exact authorized payload is the one enqueued and executed.
- **BLOCK:** no ACT is enqueued and no protected order effect occurs.
- **EGA unavailable / timeout / malformed response:** fail closed; no protected effect.
- **Post-authorization mutation:** altered execution-relevant payload is rejected or reauthorized.
- **Queue-to-node integrity:** alteration of ACT/result fields in transit cannot be accepted as the previously authorized action.
- **Authority/context failure:** invalid, expired, revoked, replayed, or stale authority/context does not proceed.
- **Independent controls remain:** ComOS billing, balance, autonomy, and settlement checks continue to run; EGA does not replace them.

## 5. Handoff status

**Ready to discuss the interface; not yet ready to claim completed integration.**

Before asking ComOS to implement, the handoff needs one concrete mapping from the live `order_create` payload to EGA intent/authority fields. That mapping must be checked against the actual ComOS source and the served version. The ComOS-side acceptance tests above then become the completion criteria.

No claim is made here that the remote node currently verifies an EGA authorization token or that its transport signature covers the full ACT payload. Those are explicit integration questions, not capabilities provided by this HTTP adapter.
