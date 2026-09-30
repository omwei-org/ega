# Observer → EGA Evidence Interoperability Contract v1

This document defines the minimum evidence envelope needed for an Observer to interoperate with EGA without coupling the Observer to EGA's governance model.

The contract is deliberately narrower than both the Observer's internal governance/evidence model and EGA's authority model.

## 1. Contract boundary

The contract carries evidence only.

It MUST NOT carry:

- execution authority;
- authorization decisions;
- materiality decisions;
- commit-condition promotion;
- policy decisions;
- BLOCK/COMMIT decisions;
- enforcement instructions.

The responsibility split is:

~~~
Observer
  → reports evidence

Evidence contract
  → transports evidence identity, state, temporal and integrity semantics

Adapter
  → normalizes the contract into the consumer's internal representation

EGA
  → determines material relevance and execution authority

AEE
  → expresses which selected properties must remain true at commit

Execution boundary
  → evaluates those properties

SLC
  → enforces the declared boundary non-bypassably
~~~

## 2. Minimum evidence envelope

| Field | Meaning |
|---|---|
| \`schema_version\` | Version identifying the semantics of the envelope fields |
| \`evidence_id\` | Stable identity of the observation/evidence item |
| \`subject\` | Subject or target to which the observation applies |
| \`state\` | Observed state, including explicit \`UNKNOWN\` where applicable |
| \`value\` | Observed value, when applicable |
| \`observed_at\` | Time at which the observation was made |
| \`freshness\` | Source-reported freshness classification |
| \`temporal_basis\` | Temporal basis used to interpret the observation/freshness metadata |
| \`provenance\` | Source identity/provenance |
| \`uncertainty\` | Uncertainty/confidence information when the source provides it |
| \`integrity_ref\` | Integrity reference over the canonical evidence representation |

\`uncertainty\` is optional because not every source can provide it. \`UNKNOWN\` is an explicit evidence state, not an authorization result.

## 3. Temporal semantics

\`observed_at\` MUST be an ISO-8601 timestamp with an explicit timezone.

The envelope carries the source observation time and its temporal basis. It does not decide whether the evidence is fresh enough for a particular action.

Freshness policy remains consumer/governance-specific.

For example:

~~~
observed_at = T0
temporal_basis = source_observation_time
freshness = FRESH
~~~

EGA may later establish a condition such as:

~~~
age(observed_at) <= allowed_age
~~~

The threshold is not part of the Observer evidence contract unless a separate contract explicitly requires it.

## 4. Integrity semantics

The \`integrity_ref\` is SHA-256 over the canonical JSON representation of all evidence fields except \`integrity_ref\`.

Canonicalization uses:

- UTF-8 encoding;
- JSON object keys sorted lexicographically;
- compact separators \`,\` and \`:\`;
- \`ensure_ascii=false\`.

The integrity reference establishes identity/integrity of the evidence representation. It does not establish that the observation is true, current, materially relevant, authorized, or safe to execute.

## 5. Promotion boundary

An Observer MAY report:

~~~
state = UNKNOWN
freshness = STALE
uncertainty = 0.20
~~~

It MUST NOT report:

~~~
commit_condition = true
authority = valid
action = allowed
~~~

EGA alone determines whether an evidence property is materially relevant and whether that property becomes an explicit execution condition.

Therefore:

~~~
evidence ≠ commit condition
~~~

and:

~~~
changed evidence ≠ failed condition
~~~

A changed evidence item requires re-evaluation of the EGA-defined condition; a digest change by itself is not the semantic predicate.

## 6. Example

Observer sends:

~~~
schema_version = observer-evidence/1.0
evidence_id    = obs-valve-001
subject        = valve-v1
state          = KNOWN
value          = 20
observed_at    = 2026-09-29T14:00:00Z
freshness      = FRESH
temporal_basis = source_observation_time
provenance     = sensor-17
uncertainty    = 0.02
integrity_ref  = <sha256>
~~~

EGA may determine:

~~~
state == KNOWN
AND freshness == FRESH
AND uncertainty <= 0.10
~~~

That predicate is an EGA/AEE semantic object, not an Observer field.

If uncertainty changes from \`0.02\` to \`0.03\`, the evidence representation changes and therefore its integrity reference changes. The predicate may still hold.

If state becomes \`UNKNOWN\` or freshness no longer satisfies the EGA condition, the predicate may fail.

This distinction is the reason the evidence contract carries identity/integrity separately from the normative condition.

## 7. Interoperability property

An Observer implementing this envelope does not need to know:

- that the consumer is EGA;
- how EGA determines materiality;
- how EGA constructs an ExecutionAuthority;
- what AEE representation is used;
- which enforcement substrate is selected;
- whether enforcement is software, TEE, pipeline, MCU/secure element, or another SLC form.

The contract therefore defines an evidence interoperability seam without importing EGA governance semantics into the Observer.
