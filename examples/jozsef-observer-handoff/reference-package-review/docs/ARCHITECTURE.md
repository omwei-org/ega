# Architecture

## Pipeline

```text
catalog source (read-only, local fixture — NOT real ComOS)
        ↓  read_field(T1, SKU1, price_cents)
Observer (evidence-only)
        ↓  observe(...) → EvidenceEnvelope v1
canonicalization (nextone-canonical-json-v1) + SHA-256 integrity
        ↓
EGA seam adapter (lossless presentation)
        ↓
EGA evaluation (test-only local stand-in; real EGA unavailable)
        ↓  given independently established authorization condition
projected execution condition
        ↓
execution boundary (non-ComOS test stub in this reference)
```

## Concepts, kept strictly separate

| Concept | Owner in this reference | Meaning |
|---|---|---|
| **Evidence** | Observer (`src/nextone_interop/observer.py`) | What was observed, where, when, with what integrity. Nothing else. |
| **Policy / authorization condition** | EGA side (`tests/ega_context/authorized_price_2500.json`) | Independently established fact used at evaluation time. Never inside evidence. |
| **Authorization decision** | EGA evaluation (test stand-in) | Whether evidence satisfies the condition. Never emitted by the Observer or the seam. |
| **Verification** | `canonical.py` + `validation.py` | Schema validity + deterministic digest. Proves integrity of encoding, not policy satisfaction (INV-07). |
| **Execution** | ComOS `retail_sale` → `createBrokeredPendingOrder(...)` (real system, **not touched**) | Out of scope here; the seam never joins this path (INV-09). |

## Components

### Catalog source — `catalog_source.py`

`CatalogSource` is a read-only protocol: `read_field(tenant_id, sku, field)`
and `describe()`. The shipped implementation, `LocalJsonCatalogSource`,
reads a clearly labeled local JSON fixture with named snapshots. It is not
real ComOS and is never labeled as such. The interface is deliberately small
so a real read-only ComOS adapter can replace the fixture later without
touching the Observer. Unknown values read as `None`, which the Observer
reports as `UNKNOWN` — never as zero, false, or denied (INV-05).

### Observer — `observer.py`

Single public operation: `observe(...) → EvidenceEnvelope`. It reads the
target through the source, captures `observed_at` **from its own clock**
(see `clock.py` below), records the evidence-only `temporal_basis`,
provenance, explicit uncertainty, derives the strong `evidence_id`, then
canonicalizes and hashes the payload. No authorization lookup, no policy
interpretation, no FRESH/STALE, no execution (AT-11, AT-12). The class
intentionally has no method named authorize/approve/allow/deny/execute/
commit/grant/resolve_policy/evaluate_policy; tests enforce this.

### Clock — `clock.py`

`Clock` protocol: `now_utc() -> datetime`. Default: `SystemUtcClock` (system
UTC clock). Tests and deterministic fixture construction inject
`FixedUtcClock` (frozen, timezone-aware UTC only — naive datetimes are
rejected; offset-aware datetimes are normalized to UTC). Normal `observe()`
has **no timestamp parameter**: callers cannot inject arbitrary observation
times. The fixture/historical construction path is clearly separated — it
injects a `FixedUtcClock` and still flows through the same `observe()`
method, so there is exactly one envelope-assembly path.

### EvidenceEnvelope v1 — `schemas/evidence-envelope-v1.schema.json`

Draft 2020-12 schema, closed (`additionalProperties: false`), `KNOWN`
requires non-null `observed_value`, `UNKNOWN` requires null. See
[EVIDENCE_CONTRACT.md](EVIDENCE_CONTRACT.md).

### Canonicalization + integrity — `canonical.py`

`nextone-canonical-json-v1`: payload excluding `integrity`, deterministic
key order (Unicode code points, recursive), compact separators, UTF-8,
SHA-256 hex prefixed with `sha256:`. The digest is never self-referential
(AT-07).

### EGA seam — `ega_seam.py`

`EgaSeamAdapter.present(envelope)` is **fail-closed** and validates in this
exact order (including evidence identity consistency):

1. EvidenceEnvelope v1 JSON Schema validation — a malformed object cannot
   pass merely because it carries a valid digest for its malformed payload
   (including the semantic RFC 3339 date-time check on `observed_at`);
2. semantic / architectural-invariant validation:
   - forbidden-semantics scan — recursive denylist for authorization
     semantics the schema cannot express at arbitrary depth;
   - `evidence_id` consistency — the seam independently re-derives the
     expected identifier from the envelope's identity fields using the same
     authoritative `derive_evidence_id` as the Observer generation path and
     compares it to the supplied id; a mismatch fails closed and the id is
     never silently repaired, overwritten, or regenerated;
3. canonical integrity verification (the object must hash to its own
   documented digest, INV-07);
4. presentation / handoff — a deep-copied, byte-for-byte
   semantics-preserving copy (INV-08).

A failure at any step rejects with a precise local error; nothing is
silently repaired. `present_all` keeps conflicting observations separate —
no merge, no winner, no averaging (INV-06, INV-08). The seam adds no fields
and removes none.

### EGA evaluation and execution boundary (test-only)

`tests/ega_evaluation_harness.py` and `tests/ega_context/` stand in for the
EGA side so tests can demonstrate the frozen temporal split: the evaluator
applies freshness (`check_freshness`) and the independently established
value condition (`check_value_condition`) at evaluation time. The
`ExecutionBoundaryStub` only records a projected execution condition; it is
a non-ComOS test boundary and no protected operation is validated.

## EGA compatibility status

Target baseline: commit `12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7`. The EGA
repository was **not available** in the workspace used to build this
reference, so the exact EGA adapter contract could not be inspected and
compatibility was **not executed**. Nothing about EGA was invented or
modified (INV-12). See [EGA_COMPATIBILITY.md](EGA_COMPATIBILITY.md).

## Isolation (INV-11)

The project runs and tests without the live/development NextOne Observer,
without EGA, without ComOS, and without network access. AT-17 guards
demonstrate that the generation workflow writes only inside the project.
