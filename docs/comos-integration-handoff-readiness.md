# ComOS integration handoff readiness

Status: EGA HTTP gate exists; complete order-effect binding is not yet implementation-ready.

## Verified EGA contract

The current EGA service accepts POST /v1/evaluate with { intent, authority, context_epoch }. Its response is { decision, reason, applied, effect }. The adapter accepts only COMMIT, applied=true, a non-empty reason, and effect NONE or NOT_EXECUTED. Other responses and transport errors fail closed.

The EGA service models intent parameters as items[{product_id, quantity}], optional expected_total_coms, and optional command_id/action_digest. Its conversion function reconstructs these declared fields, and the authority comparison requires the resulting parameter object to match the authority parameters exactly. command_id/action_digest are optional for backward compatibility; the ComOS node-effect profile must supply both. The digest is only an identifier: the trusted issuer must validate the scope before signing authority.

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

## Canonical node action digest (v1)

The TypeScript integration now exports canonicalActionDigest(act, nodePricing). The canonical projection is:

- schema: "comos-action-digest-v1"
- act: the exact ACT object received by the node
- node_pricing: the node-computed per-product unit prices and total_coms

Canonical bytes are UTF-8 JSON with lexicographically sorted object keys, compact separators, preserved array order, and safe integer numbers only. SHA-256 is computed over those bytes. A shared TypeScript/Python test vector is pinned in the integration tests.

The digest is not a signature, a permit, or evidence that the issuer approved the action. The issuer must independently validate tenant, action, product IDs, quantities, and total against operator-configured scope, recompute the digest, and sign a short-lived authority containing command_id and action_digest. The node gate must derive the same values from the ACT and node pricing at execution time. Do not place the issuer private key in the node runtime.

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
- Node action digest: the same canonical projection produces the same digest in Python and TypeScript; changing ACT or node prices changes it.
- Issuer scope denial: unknown tenant/product, quantity cap, or total cap violation results in no authority.
- Authority binding: changing command_id or action_digest between issuer and gate blocks.
- Authority/context invalidity, expiry, revocation, replay or staleness: fail closed.
- Existing billing, balance and settlement checks remain active.

## Handoff status

Not yet implementation-ready. The EGA interface and public ComOS input schema are known, but the current internal handler that transforms order_create into the final broker ACT is not available in the public connector repository.

Next dependency: inspect the current internal order_create handler and its final broker/node payload. Confirm which fields are transformed, defaulted or added. Then implement and test a complete EGA effect projection before sending ComOS the final implementation request.

No claim is made that the remote node currently verifies an EGA authorization token or that its transport signature covers the full ACT payload.
