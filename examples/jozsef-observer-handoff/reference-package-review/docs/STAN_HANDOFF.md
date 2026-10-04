# Stan Handoff — NextOne Observer ↔ EGA Interop Reference

## 1. EvidenceEnvelope v1 summary

- Schema: `schemas/evidence-envelope-v1.schema.json` (JSON Schema Draft
  2020-12), version id `nextone.observer.evidence-envelope/1.0`, closed
  schema, fail-closed validation.
- Required fields: `schema_version`, `evidence_id`, `subject`, `target`,
  `observed_state`, `observed_value`, `observed_at`, `temporal_basis`,
  `provenance`, `uncertainty`, `integrity`.
- `KNOWN` ⇔ non-null `observed_value`; `UNKNOWN` ⇔ null (never zero/false).
- Temporal basis is evidence-only: `point_in_time` /
  `observation_completed_at` / `UTC`. No FRESH/STALE.
- `observed_at` is captured by the Observer itself from an injectable clock
  (`Clock.now_utc()`; default system UTC, tests/fixtures inject a frozen
  clock). The normal `observe()` API has no timestamp parameter. Final
  hardening: the schema validates it **semantically** — `"format":
  "date-time"` enforced by an active `jsonschema.FormatChecker` alongside
  the canonical UTC-`Z` pattern — so impossible calendar/time values
  (`2026-02-30T12:00:00Z`, `2026-13-01T00:00:00Z`, `2026-10-03T25:00:00Z`)
  are rejected at schema validation, before integrity verification, even
  with a correctly recomputed digest.
- `evidence_id` = `"ev1:" + SHA-256(nextone-canonical-json-v1(identity
  payload))` over `{identity_version, subject, target, observed_state,
  observed_value, observed_at, provenance}` — a strong observation identity,
  documented separately from the integrity payload in
  `docs/EVIDENCE_CONTRACT.md`. It is not the integrity digest and includes
  no EGA authorization state. Final identity-hardening: the id is
  deterministic, and the seam **re-derives and verifies it** at validation
  step 2 (same authoritative `derive_evidence_id` as the Observer) — a
  syntactically valid but wrong `evidence_id` with a correctly recomputed
  integrity digest is rejected, not silently repaired.
- Integrity: `nextone-canonical-json-v1` (payload excluding `integrity`,
  deterministic key order, UTF-8) + SHA-256, `sha256:<hex>`.
- The EGA seam is fail-closed, in this order: schema validation →
  semantic invariants (forbidden-semantics scan + `evidence_id`
  derivation consistency) → integrity verification → deep-copy handoff.
  Malformed objects are rejected with precise local errors, never silently
  repaired.
- Full field semantics: `docs/EVIDENCE_CONTRACT.md`.

## 2. Golden evidence object path

```text
fixtures/golden/known_price_2500.json
```

## 3. Golden evidence object contents

Tenant `T1`, SKU `SKU1`, `catalog.price_cents` observed as `2500`, state
`KNOWN`, observed at `2026-10-03T19:00:00Z` from source `local-catalog`
(read-only), uncertainty `not_supplied`, integrity
`sha256:47b7a98f1f6f1b148e21f3dc1d462b2fea53baf1ea6f172d6bec6274c07ff193`,
`evidence_id`
`ev1:1698f0884661e8010d626cbad5c1fb666858a2f0793b6e234ce891150145c320`.

## 4. Explicit statements

- The **authorized price is absent** from Observer evidence (INV-04): the
  envelope carries only the observed value.
- **FRESH/STALE is absent** from Observer evidence (INV-03): freshness is
  EGA's evaluation-time decision; see
  `fixtures/negative/older_observation_price_2500.json`.
- **Conflict resolution is absent** from the Observer (INV-06): see
  `fixtures/conflict/observation_a.json` / `observation_b.json` — two
  independent envelopes, never merged.
- The Observer remains **read-only and evidentiary**: no authorization
  methods, no execution path (AT-11, AT-12, INV-02, INV-09).

## 5. EGA baseline commit

```text
12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
```

## 6. Test result summary

Full automated suite via `python scripts/validate_all.py` (schema validation,
digest verification, determinism checks, EGA-context separation, pytest):
**all tests pass** — see `IMPLEMENTATION_REPORT.md` for exact counts and
commands.

## 7. Unresolved compatibility question

EGA compatibility was **not executed**: the EGA repository at the baseline
commit was not available in this workspace, and the exact EGA adapter
contract was **not inspected**. The Observer-side semantics to verify
against the real adapter are recorded in `docs/EGA_COMPATIBILITY.md`.
Open questions for EGA owners: does the adapter contract at that commit
accept the EvidenceEnvelope v1 fields as-is, or does it require a different
evidence-only representation? And does it consume the canonically serialized
object directly, map fields before hashing, or apply different
canonicalization requirements? `nextone-canonical-json-v1` is the standalone
Observer-side representation; EGA interoperability for the canonical
representation is not yet established.

## 8. EGA changes

**None.** No EGA source was created, modified, or patched.

## 9. Live/development NextOne Observer

**Untouched.** No live or development NextOne Observer directory, service,
database, or deployment configuration was read from, written to, restarted,
or depended upon. This project is standalone (INV-11).
