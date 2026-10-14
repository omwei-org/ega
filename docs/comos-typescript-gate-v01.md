# ComOS TypeScript → EGA HTTP gate (v0.1)

This is a Node.js/TypeScript client for EGA's `POST /v1/evaluate`. It complements the Python adapter in PR #5; it does not modify ComOS itself.

## Run its tests

With a Node version that supports built-in `fetch`, `AbortSignal.timeout`, and TypeScript stripping (Node 22.6+):

```sh
node --experimental-strip-types --test integrations/comos/ega-http-gate.test.ts
```

If using a TypeScript runner instead, run the test file with that runner's Node test integration.

## Required insertion point

For the node-side retail-sale profile, the gate belongs in the node handler immediately before `reserveInventory`, after the node has parsed the exact ACT and computed the prices that will be used for the sale. The hub remains the requester and continues to perform its own payer, price-reconciliation, and settlement checks.

The module exports:
- `canonicalActionDigest(act, nodePricing)`: SHA-256 over the exact ACT plus node-computed item unit prices and total.
- `buildComosNodeIntent(act, nodePricing, identity)`: maps the ACT and node pricing into the current EGA schema, binding `command_id`, `action_digest`, `expected_total_coms`, items, target tenant, principal, action, and environment.
- `executeAuthorizedPayload(...)`: freezes an execution payload snapshot, authorizes the derived intent, and passes that same snapshot to the callback only after COMMIT.

Expected node-side sequence:
1. Parse the received ACT and calculate node pricing from trusted node catalog state.
2. Compute the canonical digest over the ACT and those exact prices.
3. Ask a separate operator-controlled issuer for a short-lived, single-use signed authority. The issuer must independently recompute the digest and enforce tenant, product, quantity, and total limits. The issuer private key must not be present in the node runtime.
4. Build the EGA intent with `buildComosNodeIntent`, using the same ACT and pricing, and obtain the trusted context epoch for the product/catalog version.
5. Call EGA and permit no inventory reservation on BLOCK, transport failure, malformed response, digest mismatch, expiry, or stale context.
6. At the protected effect, atomically consume the one-time permit (or use an equivalent transactional guard) with the reservation. Define crash/recovery behavior so a consumed permit cannot be replayed after a crash.

The TypeScript gate and mapping helper are integration primitives, not a complete issuer, replay-safe effect guard, or ComOS patch. The internal ComOS handler is not included in this repository, so this PR does not claim that the live ComOS path calls the gate yet.

## Fail-closed behavior and limit

Only a successful HTTP response with `decision=COMMIT`, `applied=true`, a non-empty `reason`, and `effect=NONE|NOT_EXECUTED` permits the callback. BLOCK, non-2xx, timeout, network failure, malformed JSON, and unknown response shapes deny.

The payload is cloned and frozen before intent construction; the same snapshot is passed to the effect callback. This closes the ordinary object-substitution gap within this call, but it does not prove that downstream code or a remote node executes the same semantics. End-to-end conformance still requires tests against ComOS's real served `order_create` path and node-side payload binding.

Required integration tests in ComOS:
- BLOCK/timeout/malformed EGA response => no inventory reservation, order creation, or other protected node effect.
- COMMIT => the ACT and node prices used for authorization match those used by the protected effect.
- Changing command_id, tenant, product, quantity, node price, or total changes the digest or fails scope validation.
- Issuer scope denial => no signed authority and no effect.
- Replay, expiry, digest mismatch, or stale product/catalog epoch => no effect.
- Hub billing, payer balance, expected-price reconciliation, and settlement checks remain active.
