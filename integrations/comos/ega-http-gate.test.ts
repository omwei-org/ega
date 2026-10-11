import assert from "node:assert/strict";
import test from "node:test";
import { EgaAuthorizationDenied, EgaHttpGate, type JsonValue } from "./ega-http-gate.ts";

function response(body: unknown, ok = true, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const commit = {
  decision: "COMMIT",
  reason: "AUTHORITY_VALID",
  applied: true,
  effect: "NOT_EXECUTED",
};

test("BLOCK prevents the protected callback", async () => {
  let executed = false;
  const gate = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => response({
      decision: "BLOCK", reason: "SCOPE_MISMATCH",
      applied: false, effect: "NOT_EXECUTED",
    }),
  });
  await assert.rejects(() => gate.executeAuthorizedPayload({
    payload: { order_id: "o-1", items: [{ sku: "p1", quantity: 1 }] },
    authority: { authority_id: "a-1" },
    context_epoch: 7,
    buildIntent: (payload) => ({ action: "order_create", parameters: payload }),
    execute: () => { executed = true; },
  }), EgaAuthorizationDenied);
  assert.equal(executed, false);
});

test("COMMIT executes exactly the frozen payload used to derive intent", async () => {
  let posted: Record<string, unknown> | undefined;
  let executedPayload: Readonly<JsonValue> | undefined;
  const original = { order_id: "o-1", items: [{ sku: "p1", quantity: 1 }] };
  const gate = new EgaHttpGate({
    baseUrl: "http://ega.test/",
    fetchImpl: async (_url, init) => {
      posted = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return response(commit);
    },
  });
  const outcome = await gate.executeAuthorizedPayload({
    payload: original,
    authority: { authority_id: "a-1" },
    context_epoch: 7,
    buildIntent: (payload) => ({ action: "order_create", parameters: payload }),
    execute: (payload) => { executedPayload = payload; return "queued"; },
  });
  original.items[0].quantity = 99; // cannot alter the snapshot already authorized
  assert.equal(outcome.result, "queued");
  assert.deepEqual(executedPayload, {
    order_id: "o-1", items: [{ sku: "p1", quantity: 1 }],
  });
  assert.deepEqual(
    (posted?.intent as Record<string, unknown>).parameters,
    executedPayload,
  );
});

test("timeout/transport failure denies and never executes", async () => {
  let executed = false;
  const gate = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => { throw new Error("offline"); },
  });
  await assert.rejects(() => gate.executeAuthorizedPayload({
    payload: { order_id: "o-1" },
    authority: { authority_id: "a-1" },
    context_epoch: 1,
    buildIntent: (payload) => ({ action: "order_create", parameters: payload }),
    execute: () => { executed = true; },
  }), EgaAuthorizationDenied);
  assert.equal(executed, false);
});

test("malformed response and non-success HTTP status deny", async () => {
  const malformed = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => response({ decision: "COMMIT", applied: true }),
  });
  await assert.rejects(() => malformed.authorize({
    authority: {}, intent: {}, context_epoch: 1,
  }), EgaAuthorizationDenied);

  const unavailable = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => new Response("unavailable", { status: 503 }),
  });
  await assert.rejects(() => unavailable.authorize({
    authority: {}, intent: {}, context_epoch: 1,
  }), EgaAuthorizationDenied);
});
