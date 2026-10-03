# ComOS + Observer Integration Experiment Plan

**Status:** PLAN / NOT IMPLEMENTED  
**Date:** 2026-10-03

## Purpose

Test the semantic seam between execution and independent evidence using a local ComOS Node + Observer + EGA setup.

The experiment is deliberately small and local. It must not couple Observer into the ComOS authorization or execution path.

## Architectural separation

```
ComOS = execution side
Observer = independent evidence side
EGA = evaluates evidence against the independently established authorization basis
```

Primary evidence path:

```
ComOS Node
  -> local target/state
  -> Observer
  -> EvidenceEnvelope
  -> EGA
```

ComOS execution path remains independent:

```
Hub
  -> authenticated pull
  -> ComOS Node
  -> handler
  -> local effect
  -> receipt
```

Observer must never become an authorization lookup, execution authority, or permission oracle for ComOS.

## First implementation target

Do not start with payment/ledger flows.

Select one simple existing local ComOS effect/state transition, preferably equivalent to:

```
set_position(valve-v1, 20)
```

The exact ComOS effect must be chosen from the actual Node/handler implementation before coding.

## Experimental sequence

### Step 1 — Inspect actual code

Before modifying either side, identify:

1. where the ComOS Node handler performs the local state transition;
2. where the ComOS receipt is produced;
3. what local state/target can be independently observed;
4. the exact Observer evidence envelope and adapter boundary;
5. the smallest place to connect Observer without entering the ComOS execution path;
6. how both components can run locally without live infrastructure.

### Step 2 — Golden case

Execute one controlled effect.

Expected semantic flow:

```
Act: requested state = 20
ComOS: executes local handler
Actual state: 20
Observer: KNOWN + FRESH, observed state = 20
EGA: evaluates evidence against authorization predicate
```

The test must demonstrate that Observer evidence crossing the interface does not itself constitute permission.

### Step 3 — Failure cases

Run independently:

- actual state differs from intended state;
- evidence is STALE;
- evidence is UNKNOWN.

For example:

```
Act: requested state = 20
Actual state: 25
Observer: KNOWN + FRESH, observed state = 25
EGA: receives discrepancy
```

This is the key test separating an execution assertion from independently observed state.

### Step 4 — Compare execution receipt and independent evidence

Where ComOS reports state in its receipt, compare:

```
ComOS receipt state
        vs.
Observer evidence state
```

The receipt is an execution-side assertion; Observer evidence remains an independent evidentiary assertion.

## Important temporal distinction

If Observer observes only after the ComOS effect, its evidence is post-execution evidence. It cannot be treated as a pre-execution authorization input.

If we need to test EGA's pre-execution evaluation against evidence, introduce a controlled pre-state observation (or another explicitly pre-execution observation point) rather than silently treating post-execution evidence as a precondition.

## Constraints

- Keep the first implementation local.
- Do not connect to live production infrastructure.
- Do not put Observer into the ComOS authorization/execution path.
- Do not make Observer interpret domain policy.
- Do not make Observer create AEE, commit conditions, or execution authority.
- Do not infer permission merely because an Observer evidence record was successfully transported.
- Do not use evidence identity/digest changes as automatic condition failures; EGA evaluates the authorized predicate against the current evidence.
- Keep the EGA Observer adapter semantics provider-neutral.

## Success criterion

The experiment succeeds when we can show, with a minimal runnable setup, that:

1. ComOS can execute a controlled local effect independently;
2. Observer can independently observe the resulting state;
3. Observer evidence reaches EGA through the defined evidence boundary;
4. EGA evaluates that evidence against an independently established authorization basis;
5. discrepancies, stale evidence, and unknown evidence remain distinguishable;
6. neither successful transport nor Observer classification is promoted into execution permission.

## Current EGA reference point

The Observer -> EGA adapter contract was formalized on `main` at:

```
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
```

This plan should be updated as the actual ComOS and Observer code is inspected. No implementation should be inferred from this document alone.
