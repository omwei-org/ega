/**
 * TypeScript HTTP client for EGA's POST /v1/evaluate endpoint.
 *
 * This is an integration primitive, not proof that ComOS invokes it in its
 * served order_create path. The caller must derive intent from the exact
 * payload passed to executeAuthorizedPayload.
 */
import { createHash } from "node:crypto";

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface EgaPermit {
  decision: "COMMIT";
  reason: string;
  applied: true;
  effect: "NONE" | "NOT_EXECUTED";
}

export interface EgaGateOptions {
  baseUrl: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export class EgaAuthorizationDenied extends Error {
  constructor(message = "EGA did not return an unambiguous COMMIT; denied") {
    super(message);
    this.name = "EgaAuthorizationDenied";
  }
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    const encoded = JSON.stringify(value);
    if (encoded === undefined) throw new TypeError("Value is not JSON serializable");
    return encoded;
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson(object[key])}`
  ).join(",")}}`;
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) {
      deepFreeze(child);
    }
  }
  return value;
}

function fingerprint(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value)).digest("hex");
}

export class EgaHttpGate {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: EgaGateOptions) {
    if (!options.baseUrl.trim()) throw new TypeError("baseUrl is required");
    this.timeoutMs = options.timeoutMs ?? 3000;
    if (!Number.isFinite(this.timeoutMs) || this.timeoutMs <= 0) {
      throw new TypeError("timeoutMs must be positive");
    }
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async authorize(input: {
    authority: JsonValue;
    intent: JsonValue;
    context_epoch: number;
    evidence_envelopes?: JsonValue[];
  }): Promise<EgaPermit> {
    const intent = input.evidence_envelopes === undefined
      ? input.intent
      : {
          ...(input.intent as Record<string, JsonValue>),
          evidence_envelopes: input.evidence_envelopes,
        };
    let response: Response;
    let body: unknown;
    try {
      response = await this.fetchImpl(`${this.baseUrl}/v1/evaluate`, {
        method: "POST",
        headers: { "content-type": "application/json", "accept": "application/json" },
        body: JSON.stringify({
          authority: input.authority,
          intent,
          context_epoch: input.context_epoch,
        }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (!response.ok) throw new Error(`EGA HTTP ${response.status}`);
      body = await response.json();
    } catch {
      throw new EgaAuthorizationDenied("EGA unavailable or response invalid; denied");
    }

    if (body === null || typeof body !== "object" || Array.isArray(body)) {
      throw new EgaAuthorizationDenied("EGA response is not an object; denied");
    }
    const result = body as Record<string, unknown>;
    if (
      result.decision !== "COMMIT" ||
      result.applied !== true ||
      (result.effect !== "NONE" && result.effect !== "NOT_EXECUTED") ||
      typeof result.reason !== "string" ||
      result.reason.trim().length === 0
    ) {
      throw new EgaAuthorizationDenied();
    }
    return {
      decision: "COMMIT",
      reason: result.reason,
      applied: true,
      effect: result.effect,
    };
  }

  /**
   * Clone and freeze the payload, derive the EGA intent from that exact clone,
   * authorize, then pass that same immutable clone to execute. This prevents a
   * caller from authorizing one object and later substituting another.
   *
   * buildIntent must faithfully represent every execution-relevant field.
   */
  async executeAuthorizedPayload<T>(input: {
    payload: JsonValue;
    authority: JsonValue;
    context_epoch: number;
    buildIntent: (payload: Readonly<JsonValue>) => JsonValue;
    execute: (payload: Readonly<JsonValue>) => Promise<T> | T;
    evidence_envelopes?: JsonValue[];
  }): Promise<{ result: T; permit: EgaPermit }> {
    const snapshot = deepFreeze(JSON.parse(JSON.stringify(input.payload)) as JsonValue);
    const originalFingerprint = fingerprint(snapshot);
    const intent = input.buildIntent(snapshot);
    const permit = await this.authorize({
      authority: input.authority,
      intent,
      context_epoch: input.context_epoch,
      evidence_envelopes: input.evidence_envelopes,
    });

    // Defense in depth: catch accidental mutation by integration code before effect.
    if (fingerprint(snapshot) !== originalFingerprint) {
      throw new EgaAuthorizationDenied("Authorized payload changed; reauthorization required");
    }
    const result = await input.execute(snapshot);
    return { result, permit };
  }
}
