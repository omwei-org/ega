# Golden Case: Observer → EGA → AEE → Enforcement → EAtt

This example makes the Observer → EGA handoff concrete using one valve-control action and three evidence treatments:

1. Issuance evidence — supports authority issuance but is not a commit condition.
2. Commit condition — is explicitly projected into the execution boundary.
3. Condition change before commit — the changed condition causes the final check to block.

The Observer remains read-only and evidentiary. EGA establishes execution authority and determines evidence materiality. The current Python implementation represents the AEE condition seam minimally through evidence references and digests; it is not a general AEE condition evaluator.

## 1. Concrete execution attempt

The requested action is:

```
principal   = agent-123
action      = set
target      = valve-v1
position    = 20
environment = production
```

The provisioning-time authorization scope permits this action.

The Observer supplies:

```
observation_ref = obs-valve-001
target          = valve-v1
state           = KNOWN
value           = 20
freshness       = FRESH
uncertainty     = 0.02
provenance      = sensor-17
observed_at     = 2026-09-29T14:00:00Z
digest          = obs-digest-1
```

The Observer reports what it observed and the associated evidence-quality metadata. It does not report an authorization decision.

## 2. Observer → EGA handoff

The observation crosses the adapter seam:

```
ObserverObservation
        ↓
observation_to_evidence()
        ↓
EvidenceItem
```

The resulting EGA-side evidence preserves observation identity, target, state, value, freshness, uncertainty, provenance, timestamp, and digest.

The responsibility boundary is:

```
Observer:
    reports observation

Adapter:
    normalizes observation

EGA:
    determines material relevance
```

The adapter does not decide authorization, create an AEE condition, or make COMMIT/BLOCK decisions.

## 3. Variant A — issuance evidence only

EGA may use the observation when establishing authority:

```
evaluation_status = USED
role              = issuance_basis
```

The DecisionRecord therefore records that the observation was materially considered for issuance.

However:

```
aee_conditions = ()
```

The observation is not automatically a condition that must remain true at commit.

For example:

```
T0:
    uncertainty = 0.02
    digest = D1

T1:
    uncertainty = 0.90
    digest = D2
```

If uncertainty was retained only as issuance evidence, its later change does not by itself invalidate the authority. The evidence remains reconstructable through the DecisionRecord.

The important invariant is:

```
changed observation ≠ failed execution condition
```

## 4. Variant B — explicit commit condition

EGA may instead determine that a runtime property must remain applicable at the execution boundary:

```
evaluation_status = USED
role              = commit_condition
```

The authority then contains the minimal AEE-condition seam:

```
aee_conditions = ("obs-valve-001",)

aee_condition_digests = {
    "obs-valve-001": "obs-digest-1"
}
```

The semantic transition is:

```
Observer fact
     ↓
EGA materiality decision
     ↓
explicit commit-condition projection
     ↓
AEE condition
```

The observation did not become an AEE condition merely because the Observer supplied it. EGA explicitly selected it.

## 5. What the AEE condition means

The current reference implementation does not encode a general condition language such as:

```
freshness == FRESH
uncertainty <= 0.10
state == KNOWN
```

Instead, it minimally binds the selected evidence reference and digest.

Conceptually:

```
Observation:
    freshness = FRESH

AEE:
    the applicable freshness requirement must still be
    satisfied at the execution boundary
```

The current implementation demonstrates the binding seam, not the complete semantic evaluator.

## 6. Variant C — condition changes before COMMIT

Assume the observation used as a commit condition changes before execution.

At T0:

```
state     = KNOWN
freshness = FRESH
digest    = obs-digest-1
```

At T1:

```
state     = UNKNOWN
freshness = STALE
digest    = obs-digest-unknown
```

The Observer reports the new observation.

The execution boundary does not need to infer the governance reason for the condition. It verifies the condition previously bound to the execution authority.

The reference implementation compares:

```
bound digest
    vs.
current evidence digest
```

Result:

```
AEE_CONDITION_FAILED
        ↓
BLOCK
        ↓
EFFECT = NONE
```

The key point is not that UNKNOWN or STALE universally means BLOCK.

The key point is:

> The property had previously been made an explicit execution condition, and that condition can no longer be established at commit.

## 7. Final authority check

The complete commit path is:

```
PreparedAuthority
       ↓
FINAL_AUTHORITY_CHECK
       │
       ├── context still valid?
       ├── AEE conditions still satisfied?
       └── authority integrity unchanged?
              ↓
         COMMIT / BLOCK
```

For the changed observation:

```
current_evidence_digests = {
    "obs-valve-001": "obs-digest-unknown"
}
```

while the prepared authority contains:

```
"obs-valve-001": "obs-digest-1"
```

Therefore:

```
AEE_CONDITION_FAILED
```

and the commit decision is:

```
decision = BLOCK
applied  = false
effect   = NONE
```

No substitute execution path is implicitly authorized by this failure.

## 8. What each layer knows

| Layer | Knows | Does not decide |
|---|---|---|
| Observer | observed state/value, freshness, uncertainty, provenance, time, integrity reference | authorization or commit |
| Observer → EGA adapter | normalized evidence representation | materiality or authority |
| EGA | intent, authorization scope, governance decision, evidence relevance | physical enforcement |
| DecisionRecord | full evidence population considered by EGA | execution enforcement |
| AEE projection | which selected facts must remain applicable at commit | upstream governance reasoning |
| EABC / execution boundary | declared execution-boundary requirements | why governance selected them |
| SLC | how to enforce declared requirements non-bypassably | upstream policy interpretation |
| EAtt | lineage and execution outcome | new authorization |

## 9. EAtt lineage

After the execution attempt, EAtt can preserve:

```
Observer observation
        ↓
EvidenceItem
        ↓
DecisionRecord
        ↓
ExecutionAuthority
        ↓
selected evidence / AEE condition
        ↓
FINAL_AUTHORITY_CHECK
        ↓
BLOCK or COMMIT
        ↓
execution outcome
```

For the blocked case, the relevant lineage includes:

```
authority_id
authority_digest
decision_record_ref
selected_evidence_refs
prepared_context_epoch
current_context_epoch
decision = BLOCK
reason   = AEE_CONDITION_FAILED
effect   = NONE
```

This allows later reconstruction of both why the authority existed and why the execution did or did not cross the boundary.

## 10. Semantic boundary

The complete responsibility chain is:

```
Observer
    → reports

Observer → EGA adapter
    → normalizes and preserves

EGA
    → establishes authority
    → determines evidence materiality

DecisionRecord
    → preserves the full evidence population

AEE
    → carries explicitly selected execution conditions

EABC
    → defines the execution-boundary contract

SLC
    → enforces declared conditions non-bypassably

EAtt
    → preserves execution lineage
```

Core invariants:

```
observation ≠ authorization
evidence ≠ commit condition
commit condition ≠ governance reasoning
authorization ≠ enforcement
COMMIT decision ≠ EFFECT
```

## 11. What this example establishes

This case establishes the intended Observer → EGA seam without making the Observer part of EGA.

The Observer can remain an independent upstream component. The adapter can remain small. EGA remains responsible for establishing execution authority and determining which evidence is materially relevant. Only explicit EGA projection turns evidence into an execution-boundary condition.

This provides a concrete basis for a future interoperability contract without prematurely defining a full AEE condition language or a new enforcement engine.
