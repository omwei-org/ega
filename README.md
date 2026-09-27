# EGA — Execution Governance Authority

EGA is a reference architecture and open-source reference implementation for establishing explicit execution authority from Runtime AI Governance input.

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

The repository contains a minimal deterministic Python implementation.

```bash
python -m pip install -e .
pytest -q
```

The implementation intentionally stops at authority issuance. It does not execute or commit actions.

## Repository status

The reference architecture and initial RAIG → EGA interface are defined. The reference implementation is intentionally minimal and will evolve as the interfaces are frozen and validated through executable examples.

See:

- [Reference Architecture](docs/reference-architecture.md)
- [RAIG → EGA Interface](docs/raig-interface.md)
- [Execution Authority](docs/execution-authority.md)
- [Minimal Example](examples/minimal/README.md)

## Related work

- EABC: https://github.com/omwei-org/omwei-eabc
