# Golden Case: Observer → Evidence Contract → EGA → AEE → Enforcement → EAtt

This example makes the Observer → EGA handoff concrete using one valve-control action and four evidence treatments:

1. issuance evidence — supports authority issuance but is not automatically a commit condition;
2. an explicit EGA-defined commit predicate;
3. evidence changes while the predicate remains true;
4. evidence changes so the predicate fails.

The Observer remains read-only and evidentiary. The interoperable evidence contract carries evidence identity, state, temporal and integrity semantics. EGA establishes execution authority and determines evidence materiality. The AEE condition is the normative predicate selected by EGA; the Observer does not create it.

## 1. Concrete execution attempt

The requested action is:

~~~text
principal   = agent-123
action      = set
target      = valve-v1
position    = 20
environment = production
~~~

The provisioning-time authorization scope permits this action.

The Observer produces an interoperable evidence envelope:

~~~text
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

~~~text
Observer
    ↓
EvidenceEnvelope
    ↓
EGA adapter
    ↓
EvidenceItem
~~~

The current Python implementation provides this contract in `src/ega/interop.py`.

It carries:

- stable evidence identity;
- subject/target;
- observed state/value, including explicit UNKNOWN;
- observation time;
- temporal basis;
- freshness;
- provenance;
- uncertainty when available;
- source confidence when available;
- integrity reference;
- schema/version semantics.

It does not carry:

- authority;
- materiality;
- policy;
- commit-condition promotion;
- BLOCK/COMMIT;
- enforcement instructions.

The adapter validates the envelope, verifies its canonical SHA-256 integrity reference, and normalizes it into EGA's internal `EvidenceItem`. It does not decide materiality or authority.

## 3. Variant A — issuance evidence only

EGA may use the observation when establishing authority:

~~~text
evaluation_status = USED
role              = issuance_basis
~~~

The `DecisionRecord` records that the observation was considered for issuance.

However:

~~~text
aee_conditions = ()
~~~

The observation is therefore not automatically a condition that must remain true at commit.

For example:

~~~text
T0:
    uncertainty = 0.02
    integrity_ref = D1

T1:
    uncertainty = 0.90
    integrity_ref = D2
~~~

If uncertainty was retained only as issuance evidence, its later change does not by itself invalidate the authority. The evidence remains reconstructable through the `DecisionRecord`.

Invariant:

~~~text
changed evidence ≠ failed execution condition
~~~

## 4. Variant B — explicit commit predicate

EGA may determine that a runtime property must remain applicable at the execution boundary.

For example:

~~~text
evaluation_status = USED
role              = commit_condition
~~~

Conceptually, EGA projects the following predicate:

~~~text
state == KNOWN
AND freshness == FRESH
AND uncertainty <= 0.10
~~~

The semantic transition is:

~~~text
Observer evidence
     ↓
EGA materiality decision
     ↓
EGA-defined predicate
     ↓
AEE execution condition
~~~

The Observer did not create this predicate. The evidence contract contains no such normative field. EGA explicitly selects the property and makes it normative for this authority.

The current implementation represents the condition through an `AEECondition` containing the evidence reference plus the supported predicates:

~~~text
evidence_ref
state_equals
freshness_equals
uncertainty_max
~~~

The evaluator is implemented in `src/ega/aee.py`.

## 5. Variant C — evidence changes, predicate still holds

Now suppose the Observer reports a new observation before commit:

~~~text
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

The evidence representation changed:

~~~text
D1 ≠ D2
~~~

But EGA's predicate remains:

~~~text
state == KNOWN
AND freshness == FRESH
AND uncertainty <= 0.10
~~~

At T1:

~~~text
KNOWN = true
FRESH = true
0.03 <= 0.10 = true
~~~

Therefore:

~~~text
evidence changed
        ↓
predicate re-evaluated
        ↓
predicate still TRUE
        ↓
COMMIT remains semantically permissible
~~~

This is the key distinction: an evidence digest is an identity/integrity mechanism; it is not itself the normative predicate.

The current implementation explicitly supports this distinction. `evaluate_aee_condition()` evaluates the predicate against the current `EvidenceItem`; it does not require the current digest to equal the original digest.

This behavior is covered by `test_aee_predicate_survives_digest_change` in `tests/test_authority.py`.

## 6. Variant D — evidence changes and predicate fails

Assume instead:

~~~text
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

~~~text
state == KNOWN       → false
freshness == FRESH   → false
uncertainty <= 0.10  → true
~~~

The semantic result is:

~~~text
predicate FALSE
        ↓
BLOCK
        ↓
EFFECT = NONE
~~~

The important point is not that UNKNOWN or STALE universally means BLOCK.

The point is:

> The relevant property was explicitly made an execution condition, and that condition no longer holds at commit.

The current `final_authority_check()` invokes the AEE evaluator immediately before commit and returns an AEE failure when a projected condition no longer holds.

## 7. UNKNOWN is evidence, not a governance decision

An Observer may legitimately report:

~~~text
state = UNKNOWN
freshness = STALE
uncertainty = 0.20
~~~

This does not itself mean:

~~~text
authority = invalid
commit = blocked
~~~

Those are downstream decisions.

Only when EGA has projected a relevant property into the execution conditions does the execution boundary have a normative question to answer.

Therefore:

~~~text
UNKNOWN ≠ automatically BLOCK
~~~

but:

~~~text
UNKNOWN + condition requiring KNOWN
        → predicate FALSE
        → BLOCK
~~~

## 8. Final authority check

The implemented commit path is:

~~~text
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

The execution boundary does not infer why EGA selected a condition. It evaluates the condition explicitly bound to the authority.

The current `commit()` function is still a reference boundary operation: a successful COMMIT returns `effect = NOT_EXECUTED`. It does not itself execute a real-world effect.

The intended separation is:

~~~text
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
| DecisionRecord | evidence population considered by EGA | execution enforcement |
| AEE projection | which selected properties must remain true at commit | upstream governance reasoning |
| EABC / execution boundary | declared execution-boundary requirements | why governance selected them |
| SLC | how to enforce declared requirements non-bypassably | upstream policy interpretation |
| EAtt | lineage and execution outcome | new authorization |

## 10. EAtt lineage

After the execution attempt, EAtt can preserve:

~~~text
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

~~~text
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

The current implementation establishes the following responsibility chain:

~~~text
Observer
    → reports evidence

Evidence contract
    → preserves evidence identity, temporal and integrity semantics

EGA adapter
    → validates and normalizes evidence

EGA
    → establishes authority
    → determines evidence materiality

DecisionRecord
    → preserves the evidence considered by EGA

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

~~~text
observation ≠ authorization
evidence ≠ commit condition
changed evidence ≠ failed condition
commit condition ≠ governance reasoning
authorization ≠ enforcement
COMMIT decision ≠ EFFECT
~~~

## 12. Current implementation boundary

This example documents what the current reference implementation actually supports.

It supports:

1. Observer-compatible evidence ingestion through `EvidenceEnvelope`;
2. canonical evidence integrity validation;
3. normalization to `EvidenceItem`;
4. EGA-defined state/freshness/uncertainty predicates;
5. re-evaluation of those predicates against current evidence;
6. preservation of `DecisionRecord` and authority lineage;
7. blocking when an explicitly projected AEE condition fails.

It does **not** yet provide a general expression language. The current minimal value predicate is exact `value_equals` matching. For the ComOS experiment this can represent the required protected catalog state as:

~~~text
value_equals = {
    tenant_id: T1,
    sku: SKU1,
    price_cents: 2500
}
~~~

This is intentionally narrower than an arbitrary expression such as `catalog.price_cents(T1, SKU1) == 2500`. The Observer → EGA interoperability seam is implemented, and the minimum concrete value predicate needed for the first ComOS experiment is now implemented as well.

## 13. What this example establishes

The Observer can remain an independent upstream component. The evidence contract is small enough to be implemented independently of EGA's governance model. The adapter remains small. EGA remains responsible for establishing execution authority and determining which evidence properties are materially relevant. Only explicit EGA projection turns an evidence property into an execution-boundary condition.

The current implementation therefore gives us a concrete interoperability seam:

~~~text
Observer
    ↓
EvidenceEnvelope
    ↓
EGA adapter
    ↓
EvidenceItem
    ↓
EGA-defined AEE condition
    ↓
Final authority check
    ↓
COMMIT / BLOCK
~~~

The next implementation boundary is deliberately separate:

1. connect the real Observer evidence envelope to this existing seam;
2. bind its catalog observation to the `value_equals` condition;
3. run the same COMMIT/BLOCK cases against the real ComOS pre-execution catalog state.

That keeps the Observer integration test focused on interoperability rather than simultaneously changing the EGA condition language.
