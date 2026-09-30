# Golden Case: Observer → Evidence Contract → EGA → AEE → Enforcement → EAtt

This example makes the Observer → EGA handoff concrete using one valve-control action and four evidence treatments:

1. Issuance evidence — supports authority issuance but is not a commit condition.
2. Explicit commit predicate — EGA projects a property of evidence into the execution boundary.
3. Evidence change that still satisfies the predicate — the evidence digest changes, but the authority remains valid.
4. Evidence change that fails the predicate — the final check blocks.

The Observer remains read-only and evidentiary. The interoperable evidence contract carries evidence identity, state, temporal and integrity semantics. EGA establishes execution authority and determines evidence materiality. The current Python implementation still represents the AEE condition seam minimally; it is not yet a general AEE predicate evaluator.

## 1. Concrete execution attempt

The requested action is:

~~~
principal   = agent-123
action      = set
target      = valve-v1
position    = 20
environment = production
~~~

The provisioning-time authorization scope permits this action.

The Observer produces an interoperable evidence envelope:

~~~
schema_version = observer-evidence/1.0
evidence_id    = obs-valve-001
subject        = valve-v1
state          = KNOWN
value          = 20
freshness      = FRESH
temporal_basis = source_observation_time
uncertainty    = 0.02
provenance     = sensor-17
observed_at    = 2026-09-29T14:00:00Z
integrity_ref  = <sha256>
~~~

The Observer reports what it observed and the associated evidence-quality metadata. It does not report an authorization decision or commit condition.

## 2. Observer → interoperability seam → EGA

The observation crosses the generic evidence contract:

~~~
Observer
    ↓
EvidenceEnvelope
    ↓
EGA adapter
    ↓
EvidenceItem
~~~

The contract is deliberately narrower than EGA's governance model.

It carries:

- stable evidence identity;
- subject/target;
- observed state/value, including explicit UNKNOWN;
- observation time;
- temporal basis and freshness metadata;
- provenance;
- uncertainty when available;
- integrity reference;
- schema/version semantics.

It does not carry:

- authority;
- materiality;
- policy;
- commit-condition promotion;
- BLOCK/COMMIT;
- enforcement instructions.

The adapter normalizes the envelope into EGA's internal evidence model. It does not decide materiality or authority.

## 3. Variant A — issuance evidence only

EGA may use the observation when establishing authority:

~~~
evaluation_status = USED
role              = issuance_basis
~~~

The DecisionRecord therefore records that the observation was materially considered for issuance.

However:

~~~
aee_conditions = ()
~~~

The observation is not automatically a condition that must remain true at commit.

For example:

~~~
T0:
    uncertainty = 0.02
    integrity_ref = D1

T1:
    uncertainty = 0.90
    integrity_ref = D2
~~~

If uncertainty was retained only as issuance evidence, its later change does not by itself invalidate the authority. The evidence remains reconstructable through the DecisionRecord.

Invariant:

~~~
changed evidence ≠ failed execution condition
~~~

## 4. Variant B — explicit commit predicate

EGA may determine that a runtime property must remain applicable at the execution boundary.

For example:

~~~
evaluation_status = USED
role              = commit_condition
~~~

Conceptually, EGA projects the following predicate:

~~~
state == KNOWN
AND freshness == FRESH
AND uncertainty <= 0.10
~~~

The semantic transition is:

~~~
Observer evidence
     ↓
EGA materiality decision
     ↓
EGA-defined predicate
     ↓
AEE execution condition
~~~

The Observer did not create this predicate. The evidence contract contains no such field. EGA explicitly selected the property and made it normative for this authority.

The current reference implementation represents this projection minimally through:

~~~
aee_conditions = ("obs-valve-001",)

aee_condition_digests = {
    "obs-valve-001": "D1"
}
~~~

That reference/digest binding is an implementation seam, not the final semantic condition language.

## 5. Variant C — evidence changes, predicate still holds

Now suppose the Observer reports a new observation before commit:

~~~
T0:
    state       = KNOWN
    freshness   = FRESH
    uncertainty = 0.02
    integrity_ref = D1

T1:
    state       = KNOWN
    freshness   = FRESH
    uncertainty = 0.03
    integrity_ref = D2
~~~

The evidence representation changed, so:

~~~
D1 ≠ D2
~~~

But EGA's predicate remains:

~~~
state == KNOWN
AND freshness == FRESH
AND uncertainty <= 0.10
~~~

and at T1:

~~~
KNOWN = true
FRESH = true
0.03 <= 0.10 = true
~~~

Therefore:

~~~
evidence changed
        ↓
predicate re-evaluated
        ↓
predicate still TRUE
        ↓
COMMIT remains semantically permissible
~~~

This is the distinction Jozsef's example exposes: an evidence digest is an identity/integrity mechanism; it is not itself the normative predicate.

### Current implementation boundary

The current Python reference seam does not yet evaluate this predicate. Its digest comparison would treat D1 → D2 as a condition-binding change.

Therefore this variant is a **semantic target for the next AEE implementation step**, not a claim that the current implementation already performs general predicate evaluation.

## 6. Variant D — evidence changes and predicate fails

Assume instead:

~~~
T0:
    state       = KNOWN
    freshness   = FRESH
    uncertainty = 0.02
    integrity_ref = D1

T1:
    state       = UNKNOWN
    freshness   = STALE
    uncertainty = 0.03
    integrity_ref = D3
~~~

The EGA-defined predicate is now false:

~~~
state == KNOWN       → false
freshness == FRESH   → false
uncertainty <= 0.10  → true
~~~

The semantic result is:

~~~
predicate FALSE
        ↓
BLOCK
        ↓
EFFECT = NONE
~~~

The important point is not that UNKNOWN or STALE universally means BLOCK.

The point is:

> The relevant property was explicitly made an execution condition, and that condition no longer holds at commit.

## 7. UNKNOWN is evidence, not a governance decision

An Observer may legitimately report:

~~~
state = UNKNOWN
freshness = STALE
uncertainty = 0.20
~~~

This does not mean:

~~~
authority = invalid
commit = blocked
~~~

Those are downstream decisions.

Only when EGA has projected a relevant property into the execution conditions does the execution boundary have a normative question to answer.

Therefore:

~~~
UNKNOWN ≠ automatically BLOCK
~~~

but:

~~~
UNKNOWN + condition requiring KNOWN
        → predicate FALSE
        → BLOCK
~~~

## 8. Final authority check

The complete semantic commit path is:

~~~
PreparedAuthority
       ↓
FINAL_AUTHORITY_CHECK
       │
       ├── context still valid?
       ├── projected AEE predicates still satisfied?
       └── authority integrity unchanged?
              ↓
         COMMIT / BLOCK
~~~

The execution boundary does not infer why EGA selected a condition.

It evaluates the condition that was explicitly bound to the authority.

This is the intended separation:

~~~
Observer:
    what is evidenced?

EGA:
    what evidence property matters for this authority?

AEE:
    what must remain true?

Execution boundary:
    does it still hold now?

SLC:
    can that boundary be bypassed?
~~~

## 9. What each layer knows

| Layer | Knows | Does not decide |
|---|---|---|
| Observer | observed state/value, freshness, uncertainty, provenance, time, integrity reference | authorization or commit |
| Evidence contract | evidence identity, temporal basis, integrity semantics, schema/version | materiality, authority, enforcement |
| Observer → EGA adapter | normalized evidence representation | materiality or authority |
| EGA | intent, authorization scope, governance decision, evidence relevance | physical enforcement |
| DecisionRecord | full evidence population considered by EGA | execution enforcement |
| AEE projection | which selected properties must remain true at commit | upstream governance reasoning |
| EABC / execution boundary | declared execution-boundary requirements | why governance selected them |
| SLC | how to enforce declared requirements non-bypassably | upstream policy interpretation |
| EAtt | lineage and execution outcome | new authorization |

## 10. EAtt lineage

After the execution attempt, EAtt can preserve:

~~~
Observer evidence
        ↓
EvidenceEnvelope
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
~~~

For a blocked case, the relevant lineage includes:

~~~
authority_id
authority_digest
decision_record_ref
selected_evidence_refs
prepared_context_epoch
current_context_epoch
decision = BLOCK
reason   = AEE_CONDITION_FAILED
effect   = NONE
~~~

This allows later reconstruction of both why the authority existed and why the execution did or did not cross the boundary.

## 11. Semantic boundary

The complete responsibility chain is:

~~~
Observer
    → reports evidence

Evidence contract
    → preserves evidence identity, temporal and integrity semantics

EGA adapter
    → normalizes evidence

EGA
    → establishes authority
    → determines evidence materiality

DecisionRecord
    → preserves the full evidence population

AEE
    → carries explicitly selected execution predicates

EABC
    → defines the execution-boundary contract

SLC
    → enforces declared conditions non-bypassably

EAtt
    → preserves execution lineage
~~~

Core invariants:

~~~
observation ≠ authorization
evidence ≠ commit condition
changed evidence ≠ failed condition
commit condition ≠ governance reasoning
authorization ≠ enforcement
COMMIT decision ≠ EFFECT
~~~

## 12. What this example establishes

This case establishes the intended Observer → evidence interoperability seam without making the Observer part of EGA.

The Observer can remain an independent upstream component. The evidence contract is small enough to be implemented independently of EGA's governance model. The adapter remains small. EGA remains responsible for establishing execution authority and determining which evidence properties are materially relevant. Only explicit EGA projection turns an evidence property into an execution-boundary condition.

The example also exposes the next implementation boundary clearly:

1. the evidence contract defines identity, temporal and integrity semantics;
2. EGA defines the normative predicate;
3. the execution boundary evaluates that predicate;
4. SLC enforces the resulting boundary non-bypassably.

That is the semantic chain needed for a real interoperability seam without coupling Observer governance to EGA governance.
