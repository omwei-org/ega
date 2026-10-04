# EvidenceEnvelope v1 — Evidence Contract

Schema: `schemas/evidence-envelope-v1.schema.json`
Version identifier: `nextone.observer.evidence-envelope/1.0`
JSON Schema Draft 2020-12. Closed schema: additional top-level or nested
properties are rejected (fail-closed validation).

An EvidenceEnvelope is an observation. It is not, and can never become, an
authorization decision (INV-01).

## Fields

### `schema_version` (required)

Stable evidence contract version. Const:
`nextone.observer.evidence-envelope/1.0`.

### `evidence_id` (required)

Stable identifier of the observation object — never of an authorization
decision.

Derivation (validation refinement, Correction 2), deterministic:

```text
evidence_id = "ev1:" + SHA-256(nextone-canonical-json-v1(identity payload))

identity payload = {
  "identity_version": 1,
  "subject":         <envelope subject>,
  "target":          <envelope target>,
  "observed_state":  <envelope observed_state>,
  "observed_value":  <envelope observed_value>,
  "observed_at":     <envelope observed_at>,
  "provenance":      <envelope provenance>
}
```

The identity payload is documented here, separately from the integrity
payload (see `integrity` below). Coverage: at minimum subject, target,
observed state, observed value, observed time, and source/provenance
identity. Two materially different observations — different source, state,
value, or time — cannot collide on the same id merely by sharing subject,
target, and timestamp. Conflicting observations taken at the same instant
from different sources get distinct ids (see `tests/test_evidence_identity.py`).

Properties of the derivation:

* `evidence_id` is **not** `integrity.digest` — different input payloads,
  different purposes (identity vs. byte-level integrity).
* No recursive dependency: the identity payload excludes the `integrity`
  object and the id is computed before the envelope is sealed.
* No EGA authorization state participates in the id.

`evidence_id` is **not arbitrary**. The schema pattern `^ev1:[0-9a-f]{64}$`
checks only the shape; the carried id must additionally equal the
deterministic derivation above. Seam validation independently verifies this
relationship (identity-consistency refinement): `EgaSeamAdapter.present()`
re-derives the expected id from the envelope's identity fields using the
same authoritative `derive_evidence_id` (`src/nextone_interop/evidence.py`)
as the Observer generation path, and rejects — fail closed, with a precise
local error, never silently repairing, overwriting, or regenerating — any
envelope whose supplied id does not match the re-derived one. This check
runs at pipeline step 2, **before** canonical integrity verification: a
correctly recomputed `integrity.digest` cannot rescue an identity mismatch.
Identity and integrity are separate properties — a valid envelope requires
both to be internally consistent; a valid digest does not make a false id
acceptable, and a valid id does not replace digest verification.

Schema pattern: `^ev1:[0-9a-f]{64}$`.

### `subject` (required)

Observer of/for whom the value was observed. Golden path:
`{"type": "tenant", "id": "T1"}`.

### `target` (required)

What was observed. Golden path:
`{"resource": "catalog", "entity_id": "SKU1", "field": "price_cents"}`.

### `observed_state` (required)

`KNOWN` or `UNKNOWN`. Observation state only; no authorization semantics.
`KNOWN` requires non-null `observed_value`; `UNKNOWN` requires
`observed_value: null` (AT-03, AT-04).

### `observed_value` (required)

The observed catalog value. For the golden path: `2500`. This is an observed
value, **not** an authorized price, even when the two coincide (INV-04).
`UNKNOWN` is always `null` — never zero, false, or absent (INV-05).

### `observed_at` (required)

RFC 3339 / ISO 8601 UTC timestamp with mandatory `Z` suffix, e.g.
`2026-10-03T19:00:00Z`. **Captured by the Observer itself** from its
injectable clock (`Clock.now_utc()`, `src/nextone_interop/clock.py`);
normal `observe()` has no timestamp parameter, so callers cannot inject
arbitrary observation times. Deterministic fixture and
historical construction is a clearly separated path: it injects a
`FixedUtcClock` and flows through the same `observe()` method. Temporal
evidence carried by the Observer; freshness against any threshold is decided
by EGA at evaluation time (INV-03).

**Semantic validity is enforced, not just string shape** (final hardening
pass). The schema declares both the canonical UTC-`Z` pattern and
`"format": "date-time"`, and the Python validator attaches an active
`jsonschema.FormatChecker` (`src/nextone_interop/validation.py`) that
reuses the strict, range-validating `parse_rfc3339_utc` parser. The
invariant is: semantically valid RFC 3339 date-time **and** canonical UTC-`Z`
representation. Impossible calendar/time values — `2026-02-30T12:00:00Z`,
`2026-13-01T00:00:00Z`, `2026-10-03T25:00:00Z`, a non-leap-year
`2026-02-29T12:00:00Z` — are rejected at step 1 of the seam pipeline
(JSON Schema validation), **before** canonical integrity verification, even
when the envelope carries a correctly recomputed digest. Leap-day
`2024-02-29T12:00:00Z` (a real leap year) remains valid. Invalid timestamps
are never silently normalized or repaired.

### `temporal_basis` (required)

Evidence-only temporal meaning, frozen for v1:

```json
{"type": "point_in_time", "timestamp_semantics": "observation_completed_at", "clock": "UTC"}
```

MUST NOT contain `FRESH`, `STALE`, an EGA freshness threshold, a max-age
policy, or an authorization validity decision.

### `provenance` (required)

Where the observation came from:

| Key | Meaning |
|---|---|
| `source_id` | Stable source identity (e.g. `local-catalog`) |
| `source_kind` | Source kind (e.g. `local_catalog` — fixtures are never labeled real ComOS) |
| `collection_method` | Always `read_only` |
| `source_locator` | Stable reference, e.g. `catalog/T1/SKU1/price_cents` |

### `uncertainty` (required)

| Key | Meaning |
|---|---|
| `source_confidence` | Source-supplied confidence preserved as-is; `null` when none exists |
| `confidence_semantics` | How to read the field, e.g. `not_supplied` |

Confidence is never invented.

### `integrity` (required)

| Key | Meaning |
|---|---|
| `canonicalization` | Const `nextone-canonical-json-v1` |
| `algorithm` | Const `sha256` |
| `digest` | `sha256:` + 64 lowercase hex chars |

Integrity payload (distinct from the identity payload above): the complete
envelope **excluding** the `integrity` object, canonicalized (deterministic
recursive key order, compact separators, UTF-8) and hashed with SHA-256. The
digest is never self-referential (AT-07) and proves deterministic integrity
of the encoding — never policy satisfaction (INV-07).

## Example — KNOWN (golden)

`fixtures/golden/known_price_2500.json`:

```json
{
  "schema_version": "nextone.observer.evidence-envelope/1.0",
  "evidence_id": "ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320",
  "subject": {"type": "tenant", "id": "T1"},
  "target": {"resource": "catalog", "entity_id": "SKU1", "field": "price_cents"},
  "observed_state": "KNOWN",
  "observed_value": 2500,
  "observed_at": "2026-10-03T19:00:00Z",
  "temporal_basis": {"type": "point_in_time", "timestamp_semantics": "observation_completed_at", "clock": "UTC"},
  "provenance": {"source_id": "local-catalog", "source_kind": "local_catalog", "collection_method": "read_only", "source_locator": "catalog/T1/SKU1/price_cents"},
  "uncertainty": {"source_confidence": null, "confidence_semantics": "not_supplied"},
  "integrity": {"canonicalization": "nextone-canonical-json-v1", "algorithm": "sha256", "digest": "sha256:47b7a98f1f6f1b148e21f3dc1d462b2fea53baf1ea6f172d6bec6274c07ff193"}
}
```

Note: this object deliberately does **not** contain `authorized_price`,
`expected_price`, `predicate_result`, `FRESH`, `STALE`, `ALLOW`, `DENY`,
`HOLD`, `ESCALATE`, `REFUSE`, `AEE`, or any authorization/execution/commit
field (AT-02). The Observer does not know that `2500` is also the
independently authorized value (INV-04).

## Example — UNKNOWN

`fixtures/negative/unknown_price.json` has `observed_state: "UNKNOWN"` and
`observed_value: null`, with provenance and time preserved. UNKNOWN stays
UNKNOWN (INV-05).

## Conflict handling

Conflicting observations (e.g. `fixtures/conflict/observation_a.json` = 2500
and `observation_b.json` = 2600) are independent envelopes with independent
provenance, time, `evidence_id`, and digest. They are never merged, averaged,
or ranked by the Observer or the seam (INV-06). Because the identity payload
covers provenance, same-instant observations from different sources always
receive distinct ids.
