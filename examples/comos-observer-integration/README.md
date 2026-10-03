# ComOS + Observer Integration Experiment

**Status:** COMOS BASELINE CODE-VERIFIED / OBSERVER→EGA INTEGRATION NOT IMPLEMENTED  
**Date:** 2026-10-03

## Purpose

Test the semantic seam between execution and independent evidence using a local ComOS Node + Observer + EGA setup.

The experiment is deliberately small and local. Observer must remain an evidence source; it must not become part of ComOS authorization or execution.

The current document records the inspected **ComOS Node v1.0.15** execution baseline. It does not claim that Observer or SLC enforcement has already been integrated.

## Architectural separation

```
ComOS = execution substrate
Observer = independent evidence source
EGA = evaluates evidence against an independently established authorization basis
SLC / execution gate = enforcement boundary under test
```

The intended evidence path is:

```
ComOS pre-state
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
      |
      v
execution boundary
```

The ComOS execution path remains independent:

```
authenticated node pull
        ->
      ACT
        ->
 handler lookup
        ->
 execution boundary
        ->
   handler(payload)
        ->
   ComOS effect
        ->
  completion receipt
```

Observer must never become an authorization lookup, permission oracle, execution authority, or hidden part of the ComOS execution path.

---

# ComOS Baseline — Code-Verified

The baseline below is derived from direct inspection of the production ComOS Node v1.0.15 bundle `bundle/server.mjs`.

This is a **code baseline**, not an EGA/Observer result. No claim is made here that a `retail_sale` has already been executed through the local test instance.

## 1. Node-signed federation envelope

ComOS authenticates node-signed federation routes with `verifyNodeSigned`.

The canonical signed input is:

```
${node_id}|${nonce}|${timestamp}|${route}
```

The signature therefore covers:

```
node_id
nonce
timestamp
route
```

The node public key is resolved from the node identity and the signature is verified over the canonical bytes.

### Binding property

The inspected signature does **not** include the ACT payload or its execution parameters.

In particular, the following are not part of `canonicalEnvelope()`:

```
act_id
payload
tenant_id
items
outcome
result
```

Therefore the precise finding is:

> The inspected federation signature authenticates the node-scoped route invocation, but does not cryptographically bind the execution-relevant ACT payload or protected-effect parameters.

This is a **binding-property finding**. It is not, by itself, a claim that ComOS execution is unsafe or unauthorized.

---

# 2. Actual autonomous execution path

The autonomous node loop polls the federation drain route and receives queued ACTs.

The relevant sequence is:

```
Node loop
   |
   v
federation_node_drain_queue
   |
   v
authenticated node identity
   |
   v
pending ACT -> delivered
   |
   v
ACT payload
   |
   v
handlers.get(kind)
   |
   v
handler(act.payload)
   |
   v
ComOS effect
   |
   v
federation_node_act_complete
```

The important execution boundary is immediately before:

```
await handler(act.payload)
```

At that point the handler has been selected, but its effect code has not yet run.

This is the correct location for a future experimental execution gate. The gate should not be embedded inside a commerce handler.

---

# 3. Current commerce handler scope

The inspected bundle registers these commerce ACT handlers:

```
retail_sale
payment_confirm
```

The first experiment should use `retail_sale`.

Other catalogue/inventory/fulfilment operations are not the first execution target merely because they exist elsewhere in the bundle.

---

# 4. Actual `retail_sale` state dependency

`retail_sale` calls:

```
createBrokeredPendingOrder(tenantId, items, opts)
```

For each requested item, the function reads the tenant-scoped product model using:

```
tenant_id
product_id
active = true
```

It then takes the stored product `price` as the unit price.

The relevant product fields are:

```
tenant_id
product_id
name
price
currency
category
sku
digital
active
created_at
updated_at
```

### Important correction

The current ComOS implementation does **not** use the earlier illustrative state:

```
(tenant_id, sku, price_cents)
```

The real execution dependency is:

```
(tenant_id, product_id, active, price)
```

A product may also contain a `sku`, but the inspected `createBrokeredPendingOrder()` lookup is by `product_id`, not by `sku`.

Therefore the first experiment must use an actual `tenant_id` + `product_id` from the local ComOS instance.

---

# 5. Actual effect sequence

The order path performs persistent effects before returning its result.

For each sale line it first calls:

```
reserveInventory(tenantId, product_id, quantity)
```

After all required inventory has been reserved, it calculates pricing and creates the order document:

```
Orders.create(doc)
```

The order document contains, among other fields:

```
tenant_id
order_id
lines
subtotal
tax
shipping
total
currency
status = "pending"
created_at
updated_at
```

Therefore the protected execution effect is **not** just the final order-row creation.

The first persistent effect begins with inventory reservation.

This is why an execution gate placed immediately before:

```
handler(act.payload)
```

is materially different from a check inserted inside `createBrokeredPendingOrder()`: the former can block the complete handler invocation before inventory reservation or order creation begins.

---

# 6. Pricing semantics

After product prices are read, `createBrokeredPendingOrder()` calculates the subtotal and calls `resolvePrice()`.

The pricing configuration may contribute:

```
tax_rate
shipping_flat
free_shipping_over
```

The resulting values are:

```
subtotal
tax
shipping
total
```

The exact price predicate for the first EGA experiment should therefore be kept deliberately narrow.

For example:

```
authorized product price = P
observed product price = P
```

This avoids turning the first experiment into a general pricing-policy test.

---

# 7. Actual persistent storage

The inspected ComOS bundle uses MongoDB/Mongoose for the commerce models.

The local configuration inspected for the node uses:

```
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=comos-node-core
```

Tenant-scoped commerce databases follow:

```
<tenant_id>-comai
```

For example, the inspected retail tenant database is:

```
federation-retail-comai
```

The relevant product collection is:

```
retail_products
```

The inspected collection was empty at the time of baseline inspection. This means a real experiment still needs a concrete local product state; it must not invent one in the documentation.

There is no basis for the earlier SQLite `orders`-table description, so that description is removed from this document.

---

# 8. Completion receipt is post-execution

After handler execution, the node calls:

```
federation_node_act_complete
```

The `result` field is a completion receipt.

It is not the original ACT payload and must not be reused as pre-execution authorization evidence.

The temporal separation is:

```
PRE-EXECUTION
state/evidence
    ->
EGA evaluation
    ->
execution
    ->
effect
    ->
POST-EXECUTION
completion receipt / observation
```

A post-execution receipt cannot silently become the evidence used to authorize the execution that already happened.

---

# 9. Baseline boundary map

```
                    ComOS Node

 node-signed envelope
        |
        v
 authenticated federation route
        |
        v
 drain queued ACT
        |
        v
     ACT payload
        |
        v
   handlers.get(kind)
        |
        v
 [EXPERIMENTAL EXECUTION GATE]
        |
        v
  handler(act.payload)
        |
        +----------------------+
        |                      |
        v                      v
   product read          inventory reserve
        |                      |
        +----------+-----------+
                   |
                   v
             order creation
                   |
                   v
          act_complete receipt
```

The bracketed gate is **not currently an SLC implementation**. It is the candidate experimental boundary where an execution decision can be tested before the ComOS handler is invoked.

---

# Experimental target

Do not start with payment or ledger flows.

The first target should be the smallest existing `retail_sale` execution for which a concrete, independently observable pre-existing product state is available.

Preferred state:

```
tenant_id
product_id
active
price
```

The exact tenant and product must be selected from the actual local ComOS instance at test time.

Observer reports this state as evidence only.

It does not decide whether the observed price is authorized.

---

# Experimental sequence

## Step 0 — Establish a real local product baseline

Before connecting Observer or EGA:

1. identify one actual tenant;
2. identify one actual product;
3. record its current `product_id`, `active`, and `price`;
4. confirm that the product is the one actually read by the `retail_sale` path;
5. establish the controlled sale input separately.

Do not use SQLite, a synthetic database adapter, or an invented ComOS HTTP/MCP interface as a substitute for the actual implementation.

## Step 1 — Observe pre-existing state

Observer reads the product state independently:

```
tenant_id = T
product_id = P
active = true
price = X
```

Observer produces an `EvidenceEnvelope`.

The evidence path carries facts such as state, freshness, provenance, uncertainty, and source confidence.

Observer does not create authorization.

## Step 2 — Establish authorization independently

The authorization basis is established outside Observer.

For example:

```
authorized product = P
authorized price = X
required state = active
```

EGA evaluates the Observer evidence against that independently established basis.

The semantic flow is:

```
independent authorization basis
             +
       Observer evidence
             |
             v
            EGA
             |
             v
   execution conditions
```

The critical invariant remains:

> Observation is not authorization.

## Step 3 — Golden case

Use a real pre-execution state satisfying the independently established predicate.

Example:

```
Authorization basis:
  tenant = T1
  product = P1
  authorized price = 25.00
  required active = true

Observed pre-state:
  price = 25.00
  active = true
  KNOWN + FRESH

EGA:
  predicates satisfied
```

Only after the EGA decision should the controlled execution boundary be crossed.

## Step 4 — Negative cases

Repeat with controlled changes to the observed pre-state.

### VALUE MISMATCH

```
Authorized price: 25.00
Observed price:   30.00
State:            KNOWN + FRESH

EGA:
  predicate not satisfied
```

### STALE

```
Authorized price: 25.00
Observed price:   25.00
Freshness:        STALE

EGA:
  freshness predicate not satisfied
```

### UNKNOWN / INSUFFICIENT EVIDENCE

```
Authorization exists
but required evidence is unavailable or unknown

EGA:
  execution condition cannot be established
```

### CONFLICT

If Observer exposes conflicting observations, preserve that conflict as evidence semantics. Do not collapse the conflict into an authorization decision inside Observer.

---

# 10. Changed evidence semantics

A changed observation is not automatically a failed condition merely because its evidence digest changed.

The EGA condition is evaluated against the current evidence value and its predicates.

Therefore:

```
same logical evidence reference
+
new observed value/digest
+
predicate evaluation
```

is the intended model for re-evaluation.

The experiment must not implement:

```
digest changed -> BLOCK
```

as an independent rule.

The relevant question is whether the current evidence still satisfies the independently established condition.

---

# 11. Pre- vs post-execution evidence

The experiment must explicitly distinguish:

### Pre-execution

```
ComOS state
   ->
Observer evidence
   ->
EGA evaluation
   ->
execution decision
   ->
handler
   ->
effect
```

from:

### Post-execution

```
handler
   ->
effect
   ->
completion receipt / observation
```

Post-execution evidence can support audit, observation, or consistency checking.

It does not retroactively establish the authorization basis for an effect that has already happened.

---

# Constraints

- Keep the first implementation local.
- Do not connect to live production infrastructure.
- Do not put Observer into the ComOS authorization or execution path.
- Do not make Observer interpret domain policy.
- Do not make Observer create AEE, commit conditions, or execution authority.
- Do not infer permission merely because Observer evidence crossed an interface.
- Do not treat `KNOWN` or `FRESH` as normative authorization by themselves.
- Do not use evidence digest changes as automatic condition failures.
- Keep the Observer -> EGA adapter provider-neutral.
- Use the actual ComOS implementation rather than inferred HTTP, MCP, SQLite, or database interfaces.
- Do not use mock signatures, synthetic receipts, or heuristic database access as evidence for the ComOS baseline.
- Do not call the experimental execution gate an SLC unless and until it satisfies the applicable EABC/EBP conformance requirements.

---

# Success criterion

The integration experiment succeeds when a minimal runnable setup demonstrates all of the following:

1. A real local ComOS product state exists before execution.
2. Observer independently observes that pre-execution state.
3. Observer evidence reaches EGA through the defined evidence boundary.
4. EGA evaluates the evidence against an independently established authorization basis.
5. KNOWN/FRESH, STALE, UNKNOWN, mismatch, and conflict semantics remain distinguishable where applicable.
6. Observer evidence is not promoted into authorization merely by transport or classification.
7. A COMMIT path reaches the actual ComOS execution boundary and can produce the controlled local effect.
8. A BLOCK path prevents handler invocation and therefore prevents the effect from starting.
9. The resulting persistent ComOS state can be independently checked.
10. Post-execution receipts remain separate from pre-execution authorization evidence.
11. The ComOS baseline remains unchanged by the Observer evidence path.

---

# Current EGA reference point

The Observer -> EGA evidence adapter contract was formalized on `main` at:

```
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
```

The current EGA implementation contains a minimal exact-value predicate (`value_equals`) and re-evaluates that predicate against current evidence.

This document records the inspected ComOS v1.0.15 execution baseline and supersedes the earlier conceptual description that used SQLite orders and `(tenant_id, sku, price_cents)`.

**Current implementation status:** ComOS baseline code-verified; Observer -> EGA -> ComOS integration not yet implemented.

No implementation should be inferred from this document alone.
