# nextone-observer-ega-interop-reference

Standalone local reference implementation validating the evidence boundary
between a minimal read-only NextOne Observer and EGA, before any production
or live-system integration is attempted.

## Purpose

Prove the interoperability seam cleanly and deterministically:

```text
pre-existing local catalog state
        ↓
minimal read-only Observer
        ↓
EvidenceEnvelope
        ↓
EGA adapter / evaluation seam
        ↓
independently established authorization condition
        ↓
projected execution condition
        ↓
execution boundary
```

The Observer reports only what it observed. EGA decides whether the evidence
satisfies an independently established authorization condition. That
condition is never encoded into the evidence object.

## Scope

In scope: EvidenceEnvelope v1 JSON Schema (Draft 2020-12), deterministic
canonicalization (`nextone-canonical-json-v1`), SHA-256 integrity digest,
golden + negative + conflict fixtures, read-only catalog source abstraction,
minimal evidence-only Observer, narrow EGA seam adapter, full pytest suite,
and developer/architecture/test/handoff documentation.

Out of scope: production deployment, live Observer integration, policy
authoring, execution authority, ComOS/EGA redesign, federation signatures,
post-execution reconciliation and network services.

## Architecture summary

| Piece | Location | Role |
|---|---|---|
| Catalog source | `src/nextone_interop/catalog_source.py` | Read-only source interface + local fixture implementation |
| Observer | `src/nextone_interop/observer.py` | Evidence-only observation collector; owns `observed_at` via injectable clock |
| Clock | `src/nextone_interop/clock.py` | `Clock` protocol; system UTC default; frozen clock for tests/fixtures |
| Canonicalization | `src/nextone_interop/canonical.py` | `nextone-canonical-json-v1` + SHA-256 (integrity and evidence identity) |
| EGA seam | `src/nextone_interop/ega_seam.py` | Fail-closed validation (schema → semantic invariants including evidence-id consistency → integrity) + lossless handoff |
| Schema | `schemas/evidence-envelope-v1.schema.json` | EvidenceEnvelope v1 (Draft 2020-12) |
| EGA context (test-only) | `tests/ega_context/` | Independently established authorization data, **not** evidence |

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Validation refinements (2026-10-03)

Targeted validation refinements were applied to the initial reference
(`IMPLEMENTATION_REPORT.md`):

1. **Fail-closed seam** — `EgaSeamAdapter.present()` now validates in exact
   order: JSON Schema → semantic invariants (including forbidden semantics and `evidence_id` consistency) → integrity → handoff, and never
   silently repairs malformed evidence.
2. **Strong `evidence_id`** — `"ev1:" + SHA-256(identity payload)` over
   subject, target, state, value, time, and provenance; documented
   separately from the integrity digest.
3. **Clock-owned `observed_at`** — the Observer captures time itself via an
   injectable clock; normal `observe()` has no timestamp parameter.
4. **Compatibility wording** — `docs/EGA_COMPATIBILITY.md` no longer
   implies the EGA adapter contract was inspected; `nextone-canonical-json-v1`
   is documented as the standalone Observer-side representation.
5. **Clean delivery** — caches removed, `.gitignore` added, manifest
   regenerated.

## Quick start

Requires Python 3.12+.

```bash
pip install "pytest>=8,<9" "jsonschema>=4.21,<5"
python scripts/generate_golden_evidence.py   # writes fixtures/golden/known_price_2500.json
python scripts/validate_all.py               # fixtures + digests + determinism + pytest
```

or simply:

```bash
pytest -q
make test
```

## Generating the golden evidence

```bash
python scripts/generate_golden_evidence.py
```

Reads `fixtures/catalog/catalog.json` (snapshot `current`) through the
read-only source interface, observes tenant `T1` / `SKU1` / `price_cents` at
the fixed default time `2026-10-03T19:00:00Z`, and writes
`fixtures/golden/known_price_2500.json`. Output bytes and digest are
deterministic (AT-15). No observed value is hard-coded in the generation
logic (AT-14).

## What this project does **not** prove

- It does **not** prove compatibility with EGA. The EGA repository at the
  baseline commit was **not available** in this workspace; see
  [docs/EGA_COMPATIBILITY.md](docs/EGA_COMPATIBILITY.md).
- It does **not** exercise real ComOS. The catalog is a clearly labeled
  local fixture (`fixtures/catalog/catalog.json`), not ComOS data.
- It does **not** validate protected execution. The execution boundary in
  tests is a labeled non-ComOS stub.
- It does **not** grant, derive, or verify any authorization. Evidence is
  not authority (INV-01).

## Isolation warning

This project is completely separate from the live/development NextOne
Observer and from EGA. It does not import, modify, restart, or depend on any
existing NextOne or EGA component (INV-11). Do not wire it into production
paths.

## EGA baseline commit

```text
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
```

Compatibility against that commit has **not** been executed locally — see
[docs/EGA_COMPATIBILITY.md](docs/EGA_COMPATIBILITY.md).
