# ComOS integration handoff readiness

Status: EGA HTTP gate exists; complete order-effect binding is not yet implementation-ready.

## Verified EGA contract

The current EGA service accepts POST /v1/evaluate with { intent, authority, context_epoch }. Its response is { decision, reason, applied, effect }. The adapter accepts only COMMIT, applied=true, a non-empty reason, and effect NONE or NOT_EXECUTED. Other responses and transport errors fail closed.

The EGA service currently models intent parameters as items[{product_id, quantity}] plus optional expected_total_coms. Its conversion function reconstructs parameters from only those fields. The authority comparison then compares this reduced parameter object with authority parameters.

## Public ComOS order_create schema

The public connector repository ronrey/comos-mcp, file tools.json, declares these order_create inputs:
- required: tenant_id and items[{product_id, quantity}]
- optional: currency (COM or USD), customer_id, shipping_address, payment_method

Its public description says order_create performs reserve, price, settlement and paid-order persistence in one call. This is the published input schema, not the internal implementation.

Therefore, the existing EGA intent schema cannot directly represent the full public order_create input. The internal ComOS handler may also add trusted identity, resolved vendor/target, hub-derived prices and settlement fields. We must not claim the existing adapter authorizes the full effect.

## Mapping to confirm against ComOS internals

- authenticated principal: derive from validated ComOS identity
- tenant_id and resolved vendor: bind to the authorized target
- items and quantities: bind exactly
- currency: bind explicitly, including the default
- customer_id and shipping_address: bind if they affect ownership or destination
- payment_method and settlement rail: bind if they affect the payment path
- final hub-derived prices, totals and fees: bind the values actually used
- final ACT payload and node target: bind to the same canonical effect projection and verify again at execution

This is a checklist. It does not claim all fields are forwarded to the node today.

## Required flow

1. Authenticate and derive trusted identity.
2. Resolve tenant/vendor and build the final trusted order/ACT payload.
3. Derive EGA intent from that exact payload; get context_epoch from trusted state.
4. Call EGA before charging, enqueueing, order creation or another protected effect.
5. On anything other than valid COMMIT, perform no protected effect and enqueue no ACT.
6. On COMMIT, enqueue only the authorized payload; changes require reauthorization.
7. Verify payload integrity at the node execution boundary. A hub-side decision alone does not close a transport payload-substitution gap.

## Acceptance tests

- COMMIT: exact authorized effect projection matches the payload enqueued and executed.
- BLOCK, timeout, malformed response or EGA outage: no ACT enqueue and no protected effect.
- Mutation after authorization: reject or reauthorize.
- Field coverage: changing each effect-relevant field causes a mismatch unless expressly permitted.
- Queue-to-node integrity: altered ACT payload cannot be accepted as the authorized operation.
- Authority/context invalidity, expiry, revocation, replay or staleness: fail closed.
- Existing billing, balance and settlement checks remain active.

## Handoff status

Not yet implementation-ready. The EGA interface and public ComOS input schema are known, but the current internal handler that transforms order_create into the final broker ACT is not available in the public connector repository.

Next dependency: inspect the current internal order_create handler and its final broker/node payload. Confirm which fields are transformed, defaulted or added. Then implement and test a complete EGA effect projection before sending ComOS the final implementation request.

No claim is made that the remote node currently verifies an EGA authorization token or that its transport signature covers the full ACT payload.
