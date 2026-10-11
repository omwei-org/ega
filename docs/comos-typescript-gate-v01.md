# ComOS TypeScript → EGA HTTP gate (v0.1)

This is a Node.js/TypeScript client for EGA's `POST /v1/evaluate`. It complements the Python adapter in PR #5; it does not modify ComOS itself.

## Run its tests

With a Node version that supports built-in `fetch`, `AbortSignal.timeout`, and TypeScript stripping (Node 22.6+):

```sh
node --experimental-strip-types --test integrations/comos/ega-http-gate.test.ts
```

If using a TypeScript runner instead, run the test file with that runner's Node test integration.

## Required insertion point

In ComOS, invoke `executeAuthorizedPayload` only after the hub has built the trusted `order_create` payload (including hub-derived price/vendor data) and before enqueueing the ACT or creating any pending order/protected effect. Do not build an unrelated intent from caller-supplied fields.

Example integration shape:

```ts
const outcome = await egaGate.executeAuthorizedPayload({
  payload: brokerPayload,
  authority: resolvedExecutionAuthority,
  context_epoch: trustedContextEpoch,
  buildIntent: (payload) => ({
    principal: trustedPrincipal,
    action: "order_create",
    target: resolvedVendorTarget,
    parameters: { items: payload.items },
    environment: trustedEnvironment,
  }),
  execute: (authorizedPayload) => brokerActToNode(authorizedPayload),
});
```

The field names above illustrate the mapping; adapt them to the actual EGA request schema and ComOS types. The `buildIntent` function must cover every field that can change the protected effect. Do not use caller-supplied values for trusted principal, authority, or context epoch.

## Fail-closed behavior and limit

Only a successful HTTP response with `decision=COMMIT`, `applied=true`, a non-empty `reason`, and `effect=NONE|NOT_EXECUTED` permits the callback. BLOCK, non-2xx, timeout, network failure, malformed JSON, and unknown response shapes deny.

The payload is cloned and frozen before intent construction; the same snapshot is passed to the effect callback. This closes the ordinary object-substitution gap within this call, but it does not prove that downstream code or a remote node executes the same semantics. End-to-end conformance still requires tests against ComOS's real served `order_create` path and node-side payload binding.

Required integration tests in ComOS:
- BLOCK/timeout/malformed EGA response => no ACT enqueued and no pending order created.
- COMMIT => enqueued ACT payload matches the authorized intent's execution-relevant fields.
- Mutation or substitution after authorization => rejected or requires fresh authorization.
- Verify downstream node execution is bound to the authorized payload; transport metadata alone is insufficient if the result/payload is not signed or otherwise integrity-bound.
