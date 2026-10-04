# Implementation Report — NextOne Observer ↔ EGA Interop Reference

Date: 2026-10-03
Project: `nextone-observer-ega-interop-reference` (standalone, local reference)

## 1. Implementation summary

Built the standalone reference implementation exactly by design:
EvidenceEnvelope v1 (JSON Schema Draft 2020-12), deterministic
canonicalization `nextone-canonical-json-v1`, SHA-256 integrity digest,
golden + negative + conflict fixtures, read-only catalog source abstraction
with a clearly labeled local fixture, minimal evidence-only Observer, narrow
EGA seam adapter, schema/fixture/invariant/seam test suite, fixture
generation and validation entry points, and full documentation including the
Stan handoff.

A targeted validation refinement (Part II below) was then applied: fail-closed seam validation in a fixed
pipeline order, strong `evidence_id` derivation, Observer-owned `observed_at`
via injectable clock, honest EGA-compatibility wording, and a cleaned
delivery package with a regenerated manifest.

The flow `catalog state → read-only Observer → EvidenceEnvelope → EGA seam →
independently established authorization condition → projected execution
condition → execution boundary` is demonstrated with the golden path
`T1 / SKU1 / price_cents = 2500, KNOWN`.

## 2. Files created

```text
README.md
IMPLEMENTATION_REPORT.md
pyproject.toml
Makefile
.gitignore
schemas/evidence-envelope-v1.schema.json
src/nextone_interop/__init__.py
src/nextone_interop/canonical.py
src/nextone_interop/clock.py
src/nextone_interop/evidence.py
src/nextone_interop/catalog_source.py
src/nextone_interop/observer.py
src/nextone_interop/ega_seam.py
src/nextone_interop/validation.py
src/nextone_interop/fixturegen.py
fixtures/catalog/catalog.json
fixtures/golden/known_price_2500.json
fixtures/negative/older_observation_price_2500.json
fixtures/negative/known_price_2600.json
fixtures/negative/unknown_price.json
fixtures/conflict/observation_a.json
fixtures/conflict/observation_b.json
tests/conftest.py
tests/test_schema.py
tests/test_canonicalization.py
tests/test_observer.py
tests/test_invariants.py
tests/test_conflicts.py
tests/test_ega_seam.py
tests/test_evidence_identity.py
tests/test_observer_clock.py
tests/ega_evaluation_harness.py
tests/ega_context/authorized_price_2500.json
scripts/generate_golden_evidence.py
scripts/generate_fixtures.py
scripts/validate_all.py
scripts/build_manifest.py
docs/ARCHITECTURE.md
docs/EVIDENCE_CONTRACT.md
docs/TEMPORAL_SEMANTICS.md
docs/TEST_PLAN.md
docs/EGA_COMPATIBILITY.md
docs/STAN_HANDOFF.md
MANIFEST.sha256
```

## 3. Architecture decisions

- **Temporal semantics frozen** (agreed temporal semantics): Observer carries `observed_at`
  and evidence-only `temporal_basis` (`point_in_time` /
  `observation_completed_at` / `UTC`). No FRESH/STALE anywhere on the
  Observer side (INV-03); freshness is an EGA-side evaluation-time decision,
  demonstrated by the test-only evaluator.
- **Observer API surface = exactly one method** (`observe`), enforced by
  test (AT-11). No authorization vocabulary anywhere in the Observer
  (AT-12).
- **Integrity** via `nextone-canonical-json-v1`: payload excluding
  `integrity`, recursive deterministic key order, compact separators, UTF-8,
  SHA-256, `sha256:<hex>` (AT-05..AT-07).
- **Conflicts preserved independently** (INV-06): two envelopes with
  independent provenance/time/digest; the seam hands both over unchanged,
  with no merge/resolve API.
- **EGA seam is lossless presentation only** (INV-08): fail-closed schema
  validation, semantic-invariant checks (including forbidden authorization
  semantics and deterministic `evidence_id` consistency), integrity
  verification, then a semantics-preserving deep copy handoff.
- **Test-only EGA-side stand-ins** live under `tests/` (never in
  `src/`), clearly labeled: evaluation harness + non-ComOS execution
  boundary stub. No fake integration results claimed (INV-12).

## 4. EvidenceEnvelope version

`nextone.observer.evidence-envelope/1.0` — see
`schemas/evidence-envelope-v1.schema.json` and `docs/EVIDENCE_CONTRACT.md`.

## 5. EGA baseline commit

```text
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
```

## 6. Was EGA actually available and tested?

**No.** The EGA repository at the baseline commit was not available in the
workspace (verified by searching the workspace tree, the Desktop
`st observer` folder, and default sibling paths). EGA compatibility was
therefore **not executed**; the seam is a documented, fail-closed
presentation layer and `docs/EGA_COMPATIBILITY.md` records the unverified
mapping. No EGA behavior was invented or faked.

## 7. Real ComOS or local fixture?

**Local fixture.** Real ComOS was not available in the workspace.
`fixtures/catalog/catalog.json` is a clearly labeled local deterministic
catalog fixture (snapshots `current` / `prior` / `empty`), never labeled
real ComOS, read exclusively through the `CatalogSource` read-only
interface so a real ComOS adapter can replace it later. ComOS integration
was not tested and is not claimed.

## 8. Exact tests executed (initial reference, initial)

```bash
pip install "pytest>=8,<9" "jsonschema>=4.21,<5"
python scripts/generate_fixtures.py
python -m pytest -q                  # result: 55 passed in 0.20s
python scripts/validate_all.py       # result: all validations passed; pytest green
```

Final post-refinement commands and counts: Part II.6 below.

Fix during bring-up: the AT-13 static leak scan initially matched the
generic denylist key name `authorized_price` inside `ega_seam.py`'s
refusal list (false positive — the seam references the term only to refuse
it). The check now targets the EGA context fixture references
(`ega_context`, `authorized_price_2500`). Suite re-run: green.

## 9. Test counts (initial reference, initial)

```text
55 passed, 0 failed, 0 errors, 0 skipped
```

Final post-refinement count: **86 passed** — see Part II.6. No test was
silently skipped; the single external compatibility test (AT-16) executes
its documented documentation assertion because the external repository is
absent.

## 10. Warnings

- AT-16 is a documentation-status test, not an executed EGA compatibility
  run. Treat EGA compatibility as **unverified** until run against the
  baseline commit in a workspace that contains the EGA repository.
- The catalog fixture's `prior` snapshot exists only to make the
  value-mismatch and conflict fixtures source-read and deterministic; it is
  fixture data, not a claim about ComOS history.
- Python 3.12.10 / Windows (win32) was the execution environment; the suite
  is platform- and timezone-independent (all times are explicit UTC).

## 11. Unresolved items

- EGA adapter contract at commit `12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7`
  — inspect and run the external compatibility probe
  (`NEXTONE_EGA_REPO` + `tests/test_ega_seam.py::test_at_16_*` fails closed
  until a real probe is defined).
- Real ComOS read-only catalog adapter — replace the fixture source when a
  documented read-only ComOS path is available; until then, do not claim
  ComOS integration.
- Protected execution boundary — validated only as a labeled non-ComOS stub;
  real `retail_sale` / `createBrokeredPendingOrder(...)` validation is a
  later experiment, as are post-execution comparison and federation
  signatures (defined scope).

## 12. Confirmations

- **No live/development NextOne Observer was touched.** No existing
  NextOne directory, service, database, runtime evidence, or deployment
  configuration was read from, written to, restarted, or depended upon.
- **No EGA source was modified.** No EGA file was created, patched, or
  deleted; no EGA runtime was invoked.

## Part II — Seam and identity validation refinement

Applied on 2026-10-03. No invariant
was weakened; no test was removed or converted to a skip.

### II.1 Correction 1 — seam fail-closed validation

`EgaSeamAdapter.present()` (`src/nextone_interop/ega_seam.py`) now validates
in this exact order, failing closed with precise local errors and never
silently repairing malformed evidence:

1. EvidenceEnvelope v1 JSON Schema validation (Draft 2020-12, closed schema);
2. forbidden-semantic / architectural-invariant validation (recursive
   denylist scan);
3. canonical integrity verification (`nextone-canonical-json-v1` + SHA-256);
4. presentation / handoff (semantics-preserving deep copy).

Regression tests added in `tests/test_ega_seam.py`: missing required field
with a **correctly recomputed digest** for the malformed payload (proves the
schema step, not the digest, rejects it), invalid `observed_state`
(`"VERIFIED"`), UNKNOWN with non-null value, KNOWN with null value, invalid
`observed_at`, forbidden authorization semantics nested inside
`observed_value` (schema-valid, so step 2 fires), non-object input, plus a
positive golden-pass test. The existing tampered-digest test now covers
step 3 explicitly.

### II.2 Correction 2 — strong evidence_id

`evidence_id` is now `"ev1:" + SHA-256(nextone-canonical-json-v1(identity
payload))` with identity payload `{identity_version: 1, subject, target,
observed_state, observed_value, observed_at, provenance}`
(`src/nextone_interop/evidence.py::derive_evidence_id`). The identity payload
is documented separately from the integrity payload in
`docs/EVIDENCE_CONTRACT.md`. It is not the `integrity.digest` (different
input, different purpose), has no recursive dependency on the envelope, and
includes no EGA authorization state. Schema pattern updated to
`^ev1:[0-9a-f]{64}$`. All 6 fixtures regenerated; same-instant conflicting
observations from different sources now always receive distinct ids.

Tests: `tests/test_evidence_identity.py` — determinism, per-field
sensitivity (subject / target / state / value / time / provenance
`source_id`), id ≠ digest, same-timestamp conflict distinctness, on-disk
conflict independence, uniqueness across fixtures.

### II.3 Correction 3 — Observer owns observed_at

New `src/nextone_interop/clock.py`: `Clock` protocol (`now_utc() ->
datetime`), `SystemUtcClock` (default), `FixedUtcClock` (frozen;
timezone-aware only — naive rejected; offsets normalized to UTC). Normal
`Observer.observe()` has **no timestamp parameter**; time is captured from
the Observer's clock. Deterministic fixture/historical construction is a
clearly separated path: it injects a `FixedUtcClock` and flows through the
same `observe()` method, so there is exactly one envelope-assembly path.
`generate_golden_evidence.py --observed-at` continues to work through this
frozen-clock path.

Tests: `tests/test_observer_clock.py` — clock capture, system-UTC default
within the observe window, fixed-clock determinism, signature has no
timestamp parameter, arbitrary timestamps rejected (`TypeError`), naive
rejection, offset normalization, microseconds, strict RFC 3339 parsing,
fixture determinism, older-observation fixture still intentionally
generatable.

### II.4 EGA compatibility wording

`docs/EGA_COMPATIBILITY.md` rewritten: removed every "expected mapping /
expected EGA field / expected adapter behavior" phrasing. The document now
states the EGA repository at the baseline commit is unavailable locally, the
exact adapter contract was not inspected, no EGA interface was invented, and
no compatibility success is claimed. Field rows are framed as "Observer
semantics to verify against the real EGA adapter" and open "compatibility
questions to be checked against commit 12df2a7...". `nextone-canonical-json-v1` is documented as the standalone
Observer-side representation; EGA interoperability for the canonical
representation is explicitly not yet established, with the consume-directly /
map-fields / different-canonicalization question left for EGA owners.

### II.5 Clean delivery package

Removed `.pytest_cache/`, all `__pycache__/` directories, and `*.pyc` from
the delivery; added `.gitignore` covering Python caches and build artifacts.
No source, fixture, doc, report, or manifest content was removed. Manifest
regenerated after cleanup (Part II.8).

### II.6 Exact commands and results (validation refinement)

```bash
python scripts/generate_fixtures.py     # regenerated all 6 envelopes + digests
python -m pytest -q                     # 86 passed, 0 failed
python scripts/validate_all.py          # all validations passed; pytest green
```

Test count: 55 (initial) → **86 passed** after the validation refinement; 0
failed, 0 errors, 0 skipped. No test weakened; no failure converted to a
skip. `validate_all.py` confirms: all 6 envelopes schema-valid, digests
verify, no forbidden semantics, byte-identical regeneration (AT-15),
EGA-context separation (AT-13), pytest green (AT-18).

### II.7 Unchanged guarantees

`nextone-canonical-json-v1` semantics unchanged (canonicalization contract). INV-01 ..
INV-12 intact. Observer public API still exactly `{observe}` (AT-11). No
authorization vocabulary, no FRESH/STALE, no conflict resolution, no
execution path in the Observer. AT-16 still fails closed: EGA compatibility
**not executed** — repository unavailable, contract not inspected.

### II.8 Manifest

`MANIFEST.sha256` regenerated after all changes and cache cleanup
(`python scripts/build_manifest.py`), then verified entry-by-entry with
`sha256sum -c MANIFEST.sha256`.

## Part III — Timestamp semantic validation refinement

Applied on 2026-10-03 before Stan handoff. Narrowly scoped to semantic validation of `observed_at`;
no architectural semantics changed.

### III.1 Weakness found

The schema validated `observed_at` primarily by string shape (regex). Strings
such as `2026-99-99T99:99:99Z`, `2026-02-30T12:00:00Z`, or
`2026-13-01T00:00:00Z` match the UTC-`Z` shape while encoding impossible
calendar/time values, so a malformed envelope carrying one of them — together
with a correctly recomputed digest — could pass schema validation and reach
the seam handoff. That violated fail-closed semantics.

### III.2 Exact correction

- `schemas/evidence-envelope-v1.schema.json`: `observed_at` now declares
  `"format": "date-time"` **in addition to** the existing canonical
  `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$` pattern. Invariant:
  semantically valid RFC 3339 date-time **and** canonical UTC-`Z`
  representation. The `Z` canonical form is not relaxed.
- `src/nextone_interop/validation.py`: the validator is now constructed as
  `Draft202012Validator(load_schema(), format_checker=FORMAT_CHECKER)` with a
  module-level `jsonschema.FormatChecker` whose `date-time` check delegates to
  the strict, range-validating `parse_rfc3339_utc` parser from
  `src/nextone_interop/clock.py` (`ValueError` → invalid). The JSON Schema
  `format` keyword is therefore actively enforced, not annotation-only. No new
  dependency; deterministic across environments.

The seam pipeline order is unchanged — step 1 (JSON Schema validation, now
including semantic date-time checking) → step 2 (forbidden semantics) →
step 3 (integrity) → step 4 (handoff). An impossible timestamp now fails at
step 1, before integrity verification. Invalid timestamps are never silently
normalized or repaired.

### III.3 New regression tests (`tests/test_ega_seam.py`)

- `test_seam_rejects_impossible_observed_at_even_with_recomputed_digest`
  (parametrized): `2026-02-30T12:00:00Z`, `2026-13-01T00:00:00Z`,
  `2026-10-03T25:00:00Z`, `2026-99-99T99:99:99Z` — each with a correctly
  recomputed digest (`build_integrity`), each rejected by step 1.
- `test_seam_rejects_non_leap_year_february_29`: `2026-02-29T12:00:00Z`
  (2026 is not a leap year) rejected at step 1 with recomputed digest.
- `test_seam_accepts_leap_year_february_29`: `2024-02-29T12:00:00Z` (real leap
  year) accepted and presented unchanged.
- `test_seam_accepts_golden_observed_at_semantically`: positive coverage
  proving the golden fixture timestamp `2026-10-03T19:00:00Z` stays valid
  under the active format check.
- Existing `test_seam_rejects_invalid_observed_at` (`"yesterday-ish"`) kept
  unchanged.

No existing test was weakened, deleted, or converted to a skip.

### III.4 Exact commands and results (timestamp-validation refinement)

```bash
python -m pytest -q                     # 93 passed, 0 failed, 0 errors
python scripts/validate_all.py          # all validations passed; pytest green
```

Test count: 86 (post-refinement) → **93 passed** after the final hardening
pass; 0 failed, 0 errors, 0 skipped.

### III.5 Manifest

`MANIFEST.sha256` regenerated after all final validation changes and cache cleanup
(`python scripts/build_manifest.py`), then verified entry-by-entry with
`sha256sum -c MANIFEST.sha256` — every entry OK (see Part III summary below).

### III.6 Continued guarantees

- Clock architecture unchanged: `SystemUtcClock` for normal operation,
  `FixedUtcClock` for deterministic tests/fixtures; Observer-owned
  `observed_at`; no caller-controlled timestamp parameter on normal
  `observe()`.
- `evidence_id` semantics, `ev1:` prefix, identity payload,
  `nextone-canonical-json-v1`, SHA-256 integrity, conflict preservation,
  UNKNOWN semantics, provenance semantics: all unchanged.
- EGA compatibility was **not executed** locally (repository unavailable,
  contract not inspected); no new EGA compatibility result is implied.
- Real ComOS was not used; the live/development NextOne Observer was not
  touched; no EGA source was modified.

## Part IV — Identity-consistency refinement record

Applied on 2026-10-03. Narrowly
scoped to `evidence_id` derivation consistency at the seam; no other
semantics changed.

### IV.1 Weakness found

The schema verified only the `evidence_id` shape (`ev1:<64 hex>`), and
integrity verification succeeds after manually swapping in another
syntactically valid id and recomputing the envelope digest. An envelope
could therefore carry a valid schema + a syntactically valid id + a valid
recomputed digest while the id was not the deterministic derivation from the
identity fields — an identity-consistency gap at the seam.

### IV.2 Fix

`EgaSeamAdapter.present()` (`src/nextone_interop/ega_seam.py`) now runs a
new step-2 check, `_check_identity_consistency`, after the forbidden-semantics
scan and before integrity verification: it re-derives the expected
`evidence_id` from the envelope's identity fields via the same authoritative
`derive_evidence_id` (`src/nextone_interop/evidence.py`) the Observer
generation path uses, and rejects with a precise local error on mismatch.
The supplied id is never silently repaired, overwritten, or regenerated.
Generation and verification share one derivation implementation, so the two
semantics cannot diverge. `evidence_id` definition, prefix, identity payload,
canonicalization, and the identity-vs-integrity distinction are unchanged.

Pipeline order is now: 1. JSON Schema validation (incl. semantic date-time) →
2. semantic invariants (forbidden semantics + `evidence_id` consistency) →
3. canonical integrity → 4. handoff.

### IV.3 New regression tests (`tests/test_ega_seam.py`)

- `test_seam_rejects_syntactically_valid_but_wrong_evidence_id` (5.1):
  golden with `evidence_id = ev1:0000…0000`, integrity recomputed → rejected
  at step 2; integrity not used to rescue.
- `test_seam_rejects_stale_evidence_id_after_identity_field_change` (5.2,
  parametrized): `observed_value` / `provenance.source_id` / `observed_at`
  changed, old id kept, integrity recomputed → rejected at step 2.
- `test_seam_rejects_provenance_only_mutation_with_old_evidence_id` (5.3):
  `source_id` changed only, integrity recomputed → rejected at step 2.
- Golden positive: existing `test_seam_accepts_golden_envelope` still passes;
  leap-day positive updated to re-derive the id after its intentional
  `observed_at` change; tampered-digest test updated to re-derive the id so
  it still exercises step 3 integrity rejection.
- `test_seam_same_timestamp_conflicts_remain_individually_valid` (5.5):
  same timestamp, different value/source → distinct ids, distinct digests,
  both pass seam validation individually.

No existing test was weakened, deleted, or converted to a skip.

### IV.4 Exact commands and results (identity-consistency refinement)

```bash
python -m pytest -q                     # 99 passed, 0 failed, 0 errors, 0 skipped
python scripts/validate_all.py          # all validations passed; pytest green
```

Test count: 93 (post-timestamp-hardening) → **99 passed** after the identity-consistency refinement; 0 failed, 0 errors, 0 skipped. Confirmed specifically: wrong
`evidence_id` + correctly recomputed integrity digest is rejected at the
identity-consistency step.

### IV.5 Manifest

`MANIFEST.sha256` regenerated after all identity-pass changes and cache
cleanup (`python scripts/build_manifest.py`), then verified entry-by-entry
with `sha256sum -c MANIFEST.sha256` — every entry OK.

### IV.6 Continued guarantees

- `evidence_id` semantics, `ev1:` prefix, identity payload, and its
  distinction from `integrity.digest` unchanged; no recursive identity
  dependency; no EGA state in the id.
- `observed_at` behavior, `SystemUtcClock` / `FixedUtcClock`, JSON Schema
  date-time validation, UTC `Z` representation, `nextone-canonical-json-v1`,
  SHA-256 envelope integrity, UNKNOWN semantics, conflict preservation,
  authorized-value separation, read-only Observer: all unchanged.
- EGA compatibility was **not executed** locally; real ComOS was not used;
  the live/development NextOne Observer was not touched; no EGA source was
  modified.

## 13. SHA-256 hashes (post-final-hardening)

File-content hashes (note: the on-disk fixture hash differs from the
in-envelope `integrity.digest` by design — the digest covers the canonical
compact serialization excluding the `integrity` object, not the pretty-printed
fixture bytes). These reflect the final identity-consistent state of the
delivery (Part IV):

```text
c9011ea53f106e169819a3c07d665daeb1488394e602af701b6182fc021df9a9  schemas/evidence-envelope-v1.schema.json
e168a72a239b29c83944f1666b7b323c1dd5202961a13d2617c3f56ff5c6b9a1  fixtures/golden/known_price_2500.json
ae4d734d5ce87950578ec3f646d049e3e73da7dc25a660b1e9a594c44b61ffd5  docs/STAN_HANDOFF.md
4b6cbb52d6c07839906ba70fdd1b2a380c7a87a046d6e292d209d70b6e3c68e5  src/nextone_interop/validation.py
943344c9268ebb3b494928c7eb39fd9aaf0ba8629d7590d95765131d954d2c05  src/nextone_interop/ega_seam.py
```

A deterministic manifest of all project deliverables is maintained in
`MANIFEST.sha256` (regenerate with `python scripts/build_manifest.py`).
