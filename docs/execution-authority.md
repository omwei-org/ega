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


## EGA/SIF v1 implementation mapping

The current Python implementation is a **semantic reference implementation** of the EGA role and the EABC execution-boundary seam. It intentionally does not claim to be a wire-level implementation of every EGA/SIF v1 artifact.

| EGA/SIF v1 concept | Reference implementation |
|---|---|
| RAIG runtime intent | `RuntimeIntent` |
| Provisioning-time authorization scope | `AuthorizationScope` (external to EGA) |
| EGA authorization evaluation | `issue_authority()` |
| Explicit execution authority | `ExecutionAuthority` |
| AO | represented by preserved decision/scope lineage; not yet a separate runtime object |
| AEE | represented by the bounded authority/context fields; not yet a separate runtime object |
| ECT | represented by `ExecutionAuthority` at the boundary seam; not yet a separate token type |
| PREPARE | `prepare()` |
| FINAL_AUTHORITY_CHECK | `final_authority_check()` |
| COMMIT Gate decision | `commit()` |
| EAtt / failure evidence | `ExecutionAttestation` emitted by `execution_attestation()` |

This flattening is deliberate at the current reference stage. The semantic obligations are tested before introducing additional artifact types or a wire format.

In particular, `commit()` returns a decision only. It does **not** perform the external effect and therefore does not claim enforcement-boundary non-bypass, hardware-backed integrity, or tamper-resistant attestation.

AO/AEE/ECT lineage is now preserved on `ExecutionAuthority` and carried into `ExecutionAttestation` through `ao_ref`, `aee_ref`, and `ect_ref`. The EAtt remains an evidence record: it does not attest to tamper resistance, independently prove an external effect, or replace a separate provenance/verification evidence bundle.
