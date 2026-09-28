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

## EGA/SIF v1 cross-check

The public EABC EGA/SIF v1 profile defines a conceptual AO → AEE → ECT pipeline:

- **AO** carries governance-level authorization intent, including originating decision and authorization scope.
- **AEE** carries execution constraints and validity conditions that must remain applicable at the execution boundary.
- **ECT** is the execution-authority assertion presented to the enforcement boundary and, together with AO + AEE, realizes the whitepaper's portable ACT.
- **EAtt** is produced at the Commit Gate and binds the authorization artifact to the commit/execution outcome.

The current Python implementation intentionally flattens these artifacts. Therefore the mapping below is a **semantic correspondence**, not a claim that the repository currently constructs separate AO, AEE, and ECT objects.

| EGA/SIF v1 concept | Reference implementation |
|---|---|
| RAIG runtime intent | `RuntimeIntent` |
| Provisioning-time authorization scope | `AuthorizationScope` (external to EGA) |
| EGA authorization evaluation | `issue_authority()` |
| Explicit execution authority | `ExecutionAuthority` |
| AO | preserved through decision/scope lineage; not a separate runtime object |
| AEE | represented by bounded authority/context fields; not a separate runtime object |
| ECT | represented by `ExecutionAuthority` at the boundary seam; not a separate token type |
| PREPARE | `prepare()` |
| FINAL_AUTHORITY_CHECK | `final_authority_check()` |
| COMMIT Gate decision | `commit()` |
| EAtt / failure evidence | `ExecutionAttestation` emitted by `execution_attestation()` |

### Important semantic constraint

The implementation's `aee_conditions` / `aee_condition_digests` fields are a **minimal reference seam for commit-time condition checking**. They must not be read as a complete AEE model or as a general evidence engine.

In particular:

- a governance evidence item is not itself an AEE condition;
- evidence freshness affects commit only when the relevant requirement has been projected into a commit-time condition;
- `final_authority_check()` checks the declared condition seam and does not decide why a condition is materially relevant;
- the full RAIG evidence population remains EGA-side in the `DecisionRecord`;
- EAtt may reference the Decision Record and selected evidence without carrying the entire RAIG evidence population through EABC.

This preserves the architectural separation established by the EABC profile: **governance evidence explains authority issuance; AEE declares what must still be true for commit.**

## Evidence and integrity boundary

EABC Core requires evidence correlation to be intrinsically bound to the integrity protection of the artifact carrying the correlation reference. The current Python implementation records deterministic references and digests but does not provide signed or tamper-resistant artifacts.

Accordingly, the current `ExecutionAuthority` / `ExecutionAttestation` lineage is a semantic reference implementation. A conforming deployment still needs an independently verifiable integrity/binding mechanism for the relevant AO/AEE/ECT/EAtt records and their correlation references.

## Effect boundary

`commit()` returns a **commit decision** only. It does not perform the external effect.

Therefore:

```
COMMIT decision ≠ EFFECT
```

An external effect, if performed by a downstream system, requires separate execution/outcome evidence.

## Relationship to EBP

EBP specifies required properties and conformance considerations for an execution boundary. It does not determine the authorization envelope and does not normatively select software or hardware as the enforcement substrate.
