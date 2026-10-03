# ComOS + Observer Integration Experiment

**Status:** BASELINE CODE-VERIFIED / INTEGRATION NOT IMPLEMENTED  
**Date:** 2026-10-03

## Purpose

Test the semantic seam between execution and independent evidence using a local ComOS Node + Observer + EGA setup.

The experiment is deliberately small and local. It must not couple Observer into the ComOS authorization or execution path.

The first phase is now grounded in a **code-verified ComOS baseline**. EGA and Observer are not yet connected to ComOS.

## Architectural separation

```
ComOS = execution side
Observer = independent evidence side
EGA = evaluates evidence against the independently established authorization basis
```

The intended evidence path is:

```
ComOS pre-state / target
        |
        v
    Observer
        |
        v
 EvidenceEnvelope
        |
        v
      EGA
        |
        v
 execution authority / projected conditions
```

The ComOS execution path remains independent:

```
Hub
  -> authenticated pull
  -> ComOS Node
  -> ACT
  -> handler
  -> local effect
  -> receipt
```

Observer must never become an authorization lookup, execution authority, permission oracle, or hidden part of the ComOS execution path.

---

# ComOS Baseline — Code-Verified

The baseline below is derived from direct inspection of the production ComOS Node v1.0.15 bundle `bundle/server.mjs`. It is the starting point for the integration experiment; it is not an EGA/Observer result.

## 1. Federation authentication

For the `federation_node_act_complete` route, the production request is verified through `verifyNodeSigned`.

The canonical signed input is exactly:

```
{ node_id, nonce, timestamp, route }
```

with canonical representation:

```
${node_id}|${nonce}|${timestamp}|${route}
```

The verification path resolves the node's bound public key and verifies the signature over those canonical bytes.

### Finding

The federation signature authenticates the node identity, nonce, timestamp, and route.

It does **not** cryptographically cover the execution payload.

## 2. Payload binding finding

The inspected `verifyNodeSigned` implementation extracts only the envelope/signature fields required for verification:

```
node_id
nonce
timestamp
route
signature
```

Execution-relevant fields such as:

```
act_id
outcome
result
payload
tenant_id
items
```

are not included in `canonicalEnvelope()` and are not supplied to `crypto.verify()`.

Therefore:

> The inspected federation signature does not cryptographically bind the ACT payload or its execution-relevant parameters.

This is a **binding-property finding**, not a claim that ComOS execution is otherwise unauthorized or unsafe.

## 3. Execution path

The currently relevant commerce ACT handler is:

```
retail_sale
```

The handler calls:

```
createBrokeredPendingOrder(...)
```

which creates a new pending order in the local commerce database.

The `payment_confirm` handler is outside the scope of this first experiment.

## 4. Persistent execution state

The relevant SQLite table is:

```
orders (
  order_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  status TEXT NOT NULL,
  total_cents INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

The exact database interface used by the order module is `getCommerceDb()`.

The resulting `retail_sale` state therefore includes:

```
order_id
tenant_id
status = "pending"
total_cents
```

## 5. Price and total semantics

For each sale item, the execution code resolves the unit price as follows:

1. If the SKU exists in the local catalog, the catalog `price_cents` takes precedence.
2. If the SKU is absent from the catalog, the execution path may use the payload price fields.
3. Quantity is applied to the selected unit price.
4. The resulting sum is written to `orders.total_cents`.

Formally:

```
total_cents = sum(unit_price_cents * qty)
```

This matters for the next experiment because catalog price is an **execution-relevant pre-existing state dependency** that is actually read by `retail_sale`.

It is not, merely by being read, an authorization condition. Any authorization predicate over that state must be independently established and evaluated by EGA.

## 6. Baseline boundary map

```
                    ComOS Baseline

 signed federation envelope
          |
          +-- node_id
          +-- nonce
          +-- timestamp
          +-- route
          |
          v
 authenticated route
          |
          v
         ACT
          |
          v
    retail_sale handler
          |
       +--+--+
       |     |
      READ  WRITE
       |     |
    catalog orders
       |     |
       +--+--+
          |
          v
       receipt
```

The important boundary property is:

```
transport authentication
        !=
cryptographic binding of execution parameters
```

The transport signature establishes authenticated route invocation. It does not, by itself, establish a cryptographic binding between an authorization/delivery artifact and the parameters of the resulting protected effect.

---

# Experimental target

Do **not** start with payment or ledger flows.

The first integration target should be the smallest existing `retail_sale` path for which an independently observable pre-existing state is available.

The preferred dependency is the local catalog entry used by `retail_sale`, especially:

```
(tenant_id, sku, price_cents)
```

The exact SKU and tenant must be selected from the actual local ComOS instance at test time.

This replaces the earlier illustrative `set_position(valve-v1, 20)` target. That example was only a conceptual placeholder; the inspected ComOS implementation gives us a concrete existing execution path and a real pre-state dependency.

---

# Experimental sequence

## Step 0 — Preserve the ComOS baseline

Before adding Observer or EGA, retain the code-verified baseline:

1. verify the actual federation verification path;
2. verify the signed-field scope;
3. execute one real `retail_sale`;
4. verify the resulting `orders` row through the exact commerce DB interface;
5. verify the exact `total_cents` calculation semantics.

The baseline must not depend on mock signatures, synthetic receipts, heuristic DB access, or inferred exports.

## Step 1 — Observe pre-existing state

Identify one catalog state that:

- exists before execution;
- is actually read by `retail_sale`;
- can be observed independently by Observer;
- has a deterministic representation suitable for an EvidenceEnvelope.

Candidate:

```
tenant_id = T
sku       = S
price_cents = P
```

Observer reports evidence only. It does not decide whether `P` is authorized.

## Step 2 — EGA evaluation

Establish the authorization basis independently of Observer.

For example, the authorization basis may contain a predicate equivalent to:

```
catalog.price_cents(tenant, sku) == authorized_price_cents
```

Observer then supplies evidence about the current state.

The semantic flow is:

```
independently established authorization basis
                    +
             Observer evidence
                    |
                    v
                   EGA
                    |
          evaluates authorized predicate
                    |
                    v
       authority / projected conditions
```

The critical property is:

> Observer evidence is evidence. It is not authorization.

## Step 3 — Golden case

Use a pre-execution state satisfying the independently established predicate.

Example:

```
Authorization basis:
  tenant = T1
  sku = SKU-001
  authorized price = 2500 cents

Pre-state:
  catalog price = 2500 cents

Observer:
  KNOWN + FRESH
  observed price = 2500 cents

EGA:
  authorized predicate satisfied
```

Only after this evaluation should the execution-boundary experiment proceed.

## Step 4 — Negative evidence cases

Run the same structure with independently distinguishable evidence states:

### VALUE MISMATCH

```
Authorization: price = 2500
Observed:      price = 3000
Evidence:      KNOWN + FRESH

EGA:
  predicate not satisfied
```

### STALE

```
Authorization: price = 2500
Observed:      price = 2500
Evidence:      STALE

EGA:
  freshness requirement not satisfied
```

### UNKNOWN

```
Authorization: price = 2500
Observed:      UNKNOWN

EGA:
  insufficient evidence
```

### CONFLICT

If the Observer integration exposes conflicting observations, preserve the conflict as evidence semantics. Do not collapse it into an authorization decision inside the Observer.

## Step 5 — Execute and compare post-state

After the pre-execution evaluation, execute the controlled `retail_sale`.

Then compare:

```
ComOS execution result / DB state
              vs.
independent Observer evidence
```

This is a separate post-execution consistency/evidence check.

It must not be confused with the pre-execution EGA evaluation.

---

# Critical temporal distinction

If Observer observes only after the ComOS effect, its evidence is **post-execution evidence**.

It cannot silently become a pre-execution authorization input.

Therefore the experiment must explicitly distinguish:

```
PRE-EXECUTION
Observer evidence
    ->
EGA evaluation
    ->
execution
```

from:

```
EXECUTION
    ->
effect
    ->
Observer evidence
```

The second flow can support independent observation, audit, or post-execution consistency checking. It does not establish the first flow.

---

# Constraints

- Keep the first implementation local.
- Do not connect to live production infrastructure.
- Do not put Observer into the ComOS authorization/execution path.
- Do not make Observer interpret domain policy.
- Do not make Observer create AEE, commit conditions, or execution authority.
- Do not infer permission merely because Observer evidence was successfully transported.
- Do not treat Observer labels such as `KNOWN` or `FRESH` as normative authorization by themselves.
- Do not use evidence identity/digest changes as automatic condition failures; EGA evaluates the authorized predicate against current evidence.
- Keep the Observer -> EGA adapter semantics provider-neutral.
- Do not infer implementation interfaces from names; use the actual ComOS and Observer code.
- Do not use mock signatures, synthetic receipts, heuristic DB access, or fallback interfaces as evidence for the baseline.

---

# Success criterion

The integration experiment succeeds when a minimal runnable setup demonstrates all of the following:

1. ComOS executes a controlled local effect independently.
2. Observer independently observes relevant **pre-execution** state.
3. Observer evidence reaches EGA through the defined evidence boundary.
4. EGA evaluates that evidence against an independently established authorization basis.
5. KNOWN/FRESH, STALE, UNKNOWN, mismatch, and conflict semantics remain distinguishable where applicable.
6. Observer evidence is not promoted into authorization merely by transport or classification.
7. The resulting ComOS execution can be independently checked against the observed pre-state and resulting persistent state.
8. The ComOS baseline remains unchanged by the evidence path.

---

# Current EGA reference point

The Observer -> EGA evidence adapter contract was formalized on `main` at:

```
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
```

The ComOS + Observer experiment plan was previously documented at commit:

```
e4d672c9a8d2340cecd38cdfd9e4cb17979c94bd
```

This document supersedes the earlier conceptual target description by recording the inspected ComOS v1.0.15 execution baseline.

**Current implementation status:** ComOS baseline verified; Observer -> EGA -> ComOS integration not yet implemented.

No implementation should be inferred from this document alone.
