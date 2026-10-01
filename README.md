# EGA — Execution Governance Authority

EGA is a **reference architecture and semantic reference implementation** for establishing explicit execution authority from Runtime AI Governance input.

```
Runtime AI Governance
        │
        │ runtime intent + governance context + evidence
        ▼
EGA — Execution Governance Authority
        │
        │ explicit execution authority
        ▼
EABC — Execution Authority Boundary Contract
        │
        │ current execution conditions
        ▼
Enforcement Boundary
        │
        ▼
EFFECT
```

## Role

EGA is an **authorization-to-execution-authority bridge**.

It accepts runtime intent and relevant governance context, normalizes heterogeneous upstream outputs, evaluates the intent against applicable authorization scope, and produces explicit execution authority for downstream enforcement.

EGA is **authorization-complete but execution-blind**.

It does not commit effects or determine whether an authorized action may become an effect under current execution conditions.

## Evidence boundary

EGA may receive runtime evidence from an upstream Observer or equivalent evidence source through a provider-neutral evidence envelope.

The evidence contract carries evidence identity, subject or target, state or value, observation time, temporal basis, provenance, uncertainty, source confidence where provided, schema version, and an integrity reference.

The Observer reports evidence. It does not assign materiality, create execution authority, or promote evidence into a commit condition.

EGA determines which evidence is materially relevant to authorization and, where required, explicitly projects selected evidence properties into execution-boundary conditions.

An evidence change does not by itself invalidate an execution condition. The condition is evaluated against the current evidence at the execution boundary.

## What EGA does

- accepts Runtime AI Governance output or equivalent upstream authority input;
- normalizes runtime intent and governance context;
- evaluates intent against applicable authorization scope;
- derives bounded execution authority;
- preserves authorization lineage and evidence;
- hands explicit execution authority to a downstream execution boundary.

## What EGA does not do

EGA does not:

- execute actions;
- commit effects;
- determine the actual state transition;
- replace Runtime AI Governance;
- replace EABC;
- determine physical or logical execution safety;
- choose software versus hardware enforcement;
- guarantee that an authorized action will execute.

## EGA is optional to EABC

EABC is implementation-neutral and does not require EGA.

```
Authority Source → EABC → Enforcement Boundary → EFFECT
```

EGA provides one concrete architecture for the upstream authorization-to-execution-authority transition:

```
Runtime AI Governance → EGA → EABC → Enforcement Boundary → EFFECT
```

## Reference implementation

The repository contains a minimal deterministic Python **semantic reference implementation**.

```bash
python -m pip install -e ".[test]"
pytest -q
```

The implementation does not execute external actions. It includes a semantic PREPARE / FINAL_AUTHORITY_CHECK / COMMIT seam and emits `ExecutionAttestation` evidence for the resulting commit or block decision.

## Examples

- [Minimal EGA → EABC flow](examples/minimal/README.md)
- [Human boundary / substituted execution path](examples/jozsef-human-boundary/README.md)
- [Observer → EGA evidence handoff](examples/jozsef-observer-handoff/golden-case.md)

The second example models a provider-neutral runtime-control failure: a human restriction permits only execution path A, path A becomes unavailable, and a technically available substitute path B must not acquire execution authority merely because the system can execute it.

## Repository status

The reference architecture and the RAIG/Observer → EGA interoperability seams are defined. The implementation includes a minimal executable contract for runtime intent, external authorization scope, fail-closed evaluation, execution-authority issuance, and a prepare/final-check/commit seam.

See:

- [Reference Architecture](docs/reference-architecture.md)
- [RAIG → EGA Interface](docs/raig-interface.md)
- [Execution Authority](docs/execution-authority.md)
- [Minimal Example](examples/minimal/README.md)

## Related work

- EABC: https://github.com/omwei-org/omwei-eabc
