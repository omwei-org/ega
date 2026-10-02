# RAIG → EGA Interface

## Purpose

The RAIG → EGA interface defines the minimum information required for EGA to transform runtime governance output into explicit execution authority.

The interface separates **runtime governance input** from **execution authority issuance**.

RAIG does not need to expose a vendor-specific representation. An adapter may normalize upstream output into the canonical EGA input.

## Canonical input

A minimal EGA input contains:

- **principal** — the actor or agent requesting execution;
- **intent** — the concrete action, target, and parameters;
- **governance context** — applicable decision, policy, risk, or authorization references;
- **runtime context** — context relevant to the requested execution;
- **evidence/provenance** — references needed to establish origin, freshness, or traceability.

This input is **not itself execution authority**.

## Observer → EGA evidence adapter

When runtime evidence is supplied by an Observer or equivalent evidence provider, the adapter contract is deliberately narrow: **the Observer provides evidence, not authority**.

The provider-neutral evidence envelope carries:

- stable evidence / observation identifier;
- subject or target;
- observed state or value, including explicit UNKNOWN where the state cannot be established;
- observation time;
- temporal basis needed to evaluate freshness;
- source / provenance identity;
- uncertainty or source confidence where available;
- schema / version information; and
- an integrity-preserving canonical reference or digest.

The adapter preserves these evidentiary semantics when mapping into EGA's generic EvidenceItem. It does not add:

- authoritative domain policy or policy meaning;
- Policy-to-Execution Binding;
- materiality determination for the requested action;
- an authorized execution basis;
- a policy-condition satisfaction decision; or
- a commit condition or protected-effect/path enforcement claim.

Any EGA-side evaluation classification such as evaluation_status or role is assigned by EGA processing, not supplied as authority by the Observer. In particular, the adapter must not promote an observation into an AEE/commit condition merely because it was observed.

Evidence identity and condition validity are separate. A changed evidence object or digest does not by itself mean that an authorized condition has failed. EGA evaluates the authorized predicate against current evidence. For example, an uncertainty change from 0.02 to 0.03 changes the evidence representation while a condition such as uncertainty <= 0.10 may remain satisfied.

Observer-specific state labels remain evidence semantics rather than normative EGA policy. This keeps the adapter interoperable with heterogeneous Observer implementations without coupling the EGA core to a particular Observer vocabulary.

## EGA processing

EGA uses the canonical input together with an applicable, authorized execution basis and provisioning-time authorization scope to determine what execution authority may be issued.

The execution basis may be supplied by different governance or domain systems. Its representation and provisioning mechanism are deployment-specific. EGA does not silently redefine authoritative domain semantics during runtime evaluation.

```
RAIG output
    ↓
Canonical Runtime Intent
    ↓
Authorization Evaluation
    ↓
Execution Authority
```

The resulting authority preserves sufficient identity, scope, context, validity, and provenance for downstream verification.

## Separation of responsibility

| Layer | Responsibility |
|---|---|
| Runtime AI Governance | Governance decision, policy/risk context, runtime intent and evidence |
| EGA | Evaluation and issuance of explicit execution authority against an authorized execution basis |
| EABC | Binding and checking declared execution-authority conditions at the execution boundary |
| Enforcement Boundary | Independent evaluation of current execution conditions and commit |
| Effect | Externally observable result |

EGA does not select the enforcement substrate.

## Illustrative input

```json
{
  "principal": {"id": "agent-123", "type": "ai-agent"},
  "intent": {
    "action": "open",
    "target": "valve-v1",
    "parameters": {"value": "20%"}
  },
  "governance_context": {
    "decision_ref": "raig-decision-784",
    "policy_refs": ["policy:process-v3"],
    "risk_signals": []
  },
  "runtime_context": {
    "environment": "plant-7",
    "timestamp": "2026-09-27T00:00:00Z"
  },
  "evidence": {
    "provenance": "raig-system-1"
  }
}
```

## Open interface questions

The reference implementation will freeze these details incrementally:

- canonical schema;
- authority scope representation;
- validity and freshness semantics;
- evidence/provenance requirements;
- adapter requirements for heterogeneous RAIG systems;
- how a deployment supplies its authorized execution basis to EGA.
