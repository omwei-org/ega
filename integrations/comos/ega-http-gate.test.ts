import assert from "node:assert/strict";
import test from "node:test";
import { canonicalActionDigest, EgaAuthorizationDenied, EgaHttpGate, type JsonValue } from "./ega-http-gate.ts";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const intent = {
  principal: "comos-test",
  action: "order_create",
  target: "tenant:test-vendor",
  parameters: {
    items: [{ product_id: "p1", quantity: 1 }],
    command_id: "cmd-0001",
    action_digest: "0341012ba38a25a2be30c22ba24cdf2151d35fcda389c729bc6d1c0c00e5dcff",
  },
  environment: "test",
};

const authority = {
  authority_id: "auth-test",
  principal: intent.principal,
  action: intent.action,
  target: intent.target,
  parameters: intent.parameters,
  environment: intent.environment,
  source_decision: "decision-test",
};

const commit = {
  decision: "COMMIT",
  reason: "VALID",
  applied: true,
  effect: "NOT_EXECUTED",
};

test("BLOCK prevents the protected callback", async () => {
  let executed = false;
  const gate = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => response({
      decision: "BLOCK", reason: "STALE_CONTEXT",
      applied: false, effect: "NONE",
    }),
  });
  await assert.rejects(() => gate.executeAuthorizedPayload({
    payload: { items: [{ product_id: "p1", quantity: 1 }] },
    authority,
    context_epoch: 7,
    buildIntent: (payload) => ({
      ...intent,
      parameters: payload as JsonValue,
    }),
    execute: () => { executed = true; },
  }), EgaAuthorizationDenied);
  assert.equal(executed, false);
});

test("COMMIT executes the same snapshot used to derive intent", async () => {
  let posted: Record<string, unknown> | undefined;
  let executedPayload: Readonly<JsonValue> | undefined;
  const original = { items: [{ product_id: "p1", quantity: 1 }] };
  const gate = new EgaHttpGate({
    baseUrl: "http://ega.test/",
    fetchImpl: async (_url, init) => {
      posted = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return response(commit);
    },
  });
  const outcome = await gate.executeAuthorizedPayload({
    payload: original,
    authority,
    context_epoch: 7,
    buildIntent: (payload) => ({
      ...intent,
      parameters: payload as JsonValue,
    }),
    execute: (payload) => { executedPayload = payload; return "queued"; },
  });
  original.items[0].quantity = 99;
  assert.equal(outcome.result, "queued");
  assert.deepEqual(executedPayload, {
    items: [{ product_id: "p1", quantity: 1 }],
  });
  assert.deepEqual(
    ((posted?.intent as Record<string, unknown>).parameters),
    executedPayload,
  );
});

test("transport failure denies and never executes", async () => {
  let executed = false;
  const gate = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => { throw new Error("offline"); },
  });
  await assert.rejects(() => gate.executeAuthorizedPayload({
    payload: { items: [{ product_id: "p1", quantity: 1 }] },
    authority,
    context_epoch: 7,
    buildIntent: (payload) => ({ ...intent, parameters: payload as JsonValue }),
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
    authority, intent, context_epoch: 7,
  }), EgaAuthorizationDenied);

  const unavailable = new EgaHttpGate({
    baseUrl: "http://ega.test",
    fetchImpl: async () => new Response("unavailable", { status: 503 }),
  });
  await assert.rejects(() => unavailable.authorize({
    authority, intent, context_epoch: 7,
  }), EgaAuthorizationDenied);
});

test("live EGA service accepts a valid request and blocks stale context", {
  skip: !process.env.EGA_REAL_SERVICE_URL,
}, async () => {
  const gate = new EgaHttpGate({ baseUrl: process.env.EGA_REAL_SERVICE_URL! });
  const permit = await gate.authorize({ authority, intent, context_epoch: 7 });
  assert.equal(permit.decision, "COMMIT");
  assert.equal(permit.effect, "NOT_EXECUTED");

  await assert.rejects(
    () => gate.authorize({ authority, intent, context_epoch: 999 }),
    EgaAuthorizationDenied,
  );

  const mismatchedAuthority = {
    ...authority,
    parameters: {
      ...(authority.parameters as Record<string, JsonValue>),
      action_digest: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    },
  };
  await assert.rejects(
    () => gate.authorize({ authority: mismatchedAuthority, intent, context_epoch: 7 }),
    EgaAuthorizationDenied,
  );
});

test("canonical action digest matches the cross-language vector and binds ACT plus node pricing", () => {
  const act = {
    kind: "retail_sale",
    command_id: "cmd-0001",
    tenant_id: "tenant-vendor-1",
    items: [{ product_id: "p-1", quantity: 2 }],
    buyer_root: "buyer-7",
    payer_tenant_id: "tenant-buyer-7",
    brokered_sale_id: "sale-0001",
  };
  const pricing = {
    items: [{ product_id: "p-1", unit_price_coms: 125 }],
    total_coms: 250,
  };
  const digest = canonicalActionDigest(act, pricing);
  assert.equal(digest, "0341012ba38a25a2be30c22ba24cdf2151d35fcda389c729bc6d1c0c00e5dcff");
  assert.notEqual(
    canonicalActionDigest({ ...act, items: [{ product_id: "p-1", quantity: 3 }] }, pricing),
    digest,
  );
  assert.notEqual(
    canonicalActionDigest(act, { ...pricing, total_coms: 251 }),
    digest,
  );
  assert.throws(() => canonicalActionDigest(act, {
    items: [{ product_id: "p-1", unit_price_coms: 1.5 }],
    total_coms: 3,
  }), TypeError);
});
