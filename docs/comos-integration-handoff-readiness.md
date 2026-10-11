# ComOS integration handoff readiness (working note)

Status: **EGA-side HTTP gate exists, but the current order payload contract is not yet safe to hand off as implementation-ready.**
Scope: this note separates verified EGA behavior from the remaining ComOS implementation and acceptance work. It does not claim that ComOS has been modified.

## 1. Verified EGA interface

The current `src/ega/service.py` on `integration/comos-http-gate-v01` exposes `POST /v1/evaluate` with:

- request: `{ intent, authority, context_epoch }`
- response model: `{ decision, reason, applied, effect }`
- expected permit: `decision = COMMIT`, `applied = true`, non-empty `reason`, and `effect = NONE | NOT_EXECUTED`
- HTTP errors, invalid response shapes, non-COMMIT decisions, and transport failures must be treated as denial by the caller.

The service checks equality of principal, action, target, environment and converted parameters against the authority. Signed-authority validation, trusted context/version providers, authority-status checks and replay protection are dependent on the service configuration and deployment-supplied providers; the HTTP adapter does not itself supply those trust roots.

## 2. Blocking schema mismatch: execution payload vs. EGA intent

The current `RuntimeIntentRequest.parameters` schema accepts only:

```json
{
  "items": [{"product_id": "…", "quantity": 1}],
  "expected_total_coms": 123
}
```

In `_convert_intent()`, EGA explicitly reconstructs `parameters` from only `items` and optional `expected_total_coms`. Other fields are not carried into the internal `RuntimeIntent`. The authority's `parameters`, however, are accepted as a generic dictionary. Exact comparison then compares the reduced intent parameters with the authority parameters.

This creates a real integration boundary:

- If authority parameters contain extra execution-relevant fields, the exact-match check will reject the request.
- If the authority is scoped only to the reduced fields, any other values used by ComOS to determine the order effect are outside that EGA parameter equality check.
- The TypeScript helper's `buildIntent` callback is caller-defined. Its clone/freeze behavior does not prove that every execution-relevant field was included in the intent.

Therefore **do not claim that the current gate authorizes the full ComOS `order_create` payload**. Before integration, choose and test one explicit contract:
1. Extend EGA's intent schema and conversion so all execution-relevant order fields are represented and compared against authority; or
2. Define a canonical, versioned order-effect projection/digest that includes every effect-relevant field and is checked against the authority and at the execution boundary.

Which fields are effect-relevant must be confirmed against the live ComOS handler. Likely candidates to check include trusted buyer/payer, vendor/target, item identity and quantity, hub-derived price/total, currency, destination, and relevant execution context. This list is a checklist, not a claim that all fields exist in the current handler.

## 3. Required ComOS integration point

The insertion point must be confirmed against the current served `order_create` path, not inferred from older names such as `routeToolCall` or `beginPerActCharge`.

The intended sequence is:

1. Authenticate caller and derive trusted identity/scope.
2. Resolve the vendor and build the final trusted order/ACT payload, including hub-derived values.
3. Derive the EGA intent from that exact payload under the agreed complete-field contract; obtain `context_epoch` from trusted current state.
4. Call EGA before charging, queue insertion, order creation, or another protected effect.
5. On anything other than a valid COMMIT, stop without enqueuing ACT or creating the protected order.
6. On COMMIT, enqueue only the payload covered by the authorization. Any execution-relevant change requires reauthorization.
7. At the node execution boundary, verify integrity/binding of the ACT payload actually executed. A hub-side decision alone does not close a payload-substitution gap in node transport.

## 4. Acceptance tests ComOS and EGA must demonstrate

- **COMMIT:** the exact authorized effect projection/digest matches the payload enqueued and executed.
- **BLOCK:** no ACT is enqueued and no protected order effect occurs.
- **EGA unavailable / timeout / malformed response:** fail closed; no protected effect.
- **Post-authorization mutation:** altered execution-relevant payload is rejected or reauthorized.
- **Field-coverage test:** changing each effect-relevant field independently causes authorization mismatch unless the change is explicitly permitted by the authority.
- **Queue-to-node integrity:** alteration of ACT payload fields in transit cannot be accepted as the previously authorized action.
- **Authority/context failure:** invalid, expired, revoked, replayed, or stale authority/context does not proceed.
- **Independent controls remain:** ComOS billing, balance, autonomy, and settlement checks continue to run; EGA does not replace them.

## 5. Handoff status and next dependency

**Not yet implementation-ready.** The HTTP call/response shape is verified, but the full `order_create` field mapping is not verified against the current ComOS source in this working context, and the EGA intent conversion currently drops fields outside its narrow parameter schema.

The next required input is the current ComOS `order_create` implementation (especially the path that builds the final broker payload and calls `brokerActToNode`). Use it to enumerate the actual effect-relevant fields and select the complete-field contract above. Then implement and test the EGA-side schema/projection change before sending ComOS a final implementation request.

No claim is made here that the remote node currently verifies an EGA authorization token or that its transport signature covers the full ACT payload. Those remain explicit integration requirements, not capabilities provided by this HTTP adapter.
