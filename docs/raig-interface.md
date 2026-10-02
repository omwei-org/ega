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
