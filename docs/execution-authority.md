# Execution Authority

## Purpose

Execution authority is the explicit, bounded authorization that an execution boundary receives for a concrete runtime intent.

It is distinct from governance policy, runtime intent, an execution command, a prediction of future state, and a successful execution result.

## Conceptual model

```
Governance Context + Runtime Intent + Authorization Scope
                         │
                         ▼
                        EGA
                         │
                         ▼
                Execution Authority
                         │
                         ▼
                        EABC
                         │
                         ▼
                 Commit / Block
```

## Required properties

A reference execution-authority artifact should provide enough information for downstream verification of:

- principal / authority subject;
- authorized action;
- target or resource;
- execution scope and constraints;
- relevant execution context;
- validity interval or equivalent freshness mechanism;
- authorization lineage;
- integrity protection;
- correlation to upstream governance evidence.

The exact wire format is intentionally left open until the interface is frozen.

## Important invariant

A valid execution-authority artifact is **necessary but not sufficient** for an effect.

Current state, context, authority validity, execution-boundary conditions, and commit conditions remain subject to downstream verification.

> Authorization establishes what may be attempted; the execution boundary determines whether that authorized attempt may become a committed effect under current conditions.
