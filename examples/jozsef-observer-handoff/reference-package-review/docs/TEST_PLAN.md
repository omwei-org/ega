# Test Plan

Run everything:

```bash
python scripts/validate_all.py   # fixtures + digests + determinism + pytest
pytest -q                        # or directly
make test
```

Test files: `tests/test_schema.py`, `tests/test_canonicalization.py`,
`tests/test_observer.py`, `tests/test_invariants.py`,
`tests/test_conflicts.py`, `tests/test_ega_seam.py`,
`tests/test_evidence_identity.py` (Correction 2),
`tests/test_observer_clock.py`.

## Acceptance test mapping

| AT | Test(s) | Invariant(s) | Expected result |
|---|---|---|---|
| AT-01 Golden schema validity | `test_schema.py::test_at_01_golden_schema_validity` | INV-01 | golden validates against Draft 2020-12 schema |
| AT-02 Golden semantics | `test_schema.py::test_at_02_golden_semantics_present`, `..._absent` | INV-01, INV-04 | T1/SKU1/catalog/price_cents/KNOWN/2500 + all evidence fields present; none of the forbidden tokens present |
| AT-03 UNKNOWN contract | `test_schema.py::test_at_03_unknown_requires_null_value` | INV-05 | UNKNOWN validates only with null `observed_value` |
| AT-04 KNOWN contract | `test_schema.py::test_at_04_known_requires_non_null_value` | INV-05 | KNOWN with null value fails validation |
| AT-05 Digest determinism | `test_canonicalization.py::test_at_05_key_ordering_does_not_change_digest` | INV-07 | different key order → same digest |
| AT-06 Digest sensitivity | `test_canonicalization.py::test_at_06_changing_covered_fields_changes_digest` | INV-07 | changing value/time/provenance/subject/temporal basis changes digest |
| AT-07 No self-referential digest | `test_canonicalization.py::test_at_07_integrity_field_not_hashed` | INV-07 | digest input excludes `integrity` |
| AT-08 Older observation, no stale verdict | `test_conflicts.py::test_at_08_older_observation_has_no_stale_verdict` | INV-03 | same fact, older time, no FRESH/STALE |
| AT-09 Value mismatch evidence-only | `test_conflicts.py::test_at_09_value_mismatch_remains_evidence_only` | INV-01 | 2600 reported, no predicate/verdict |
| AT-10 Conflicts remain separate | `test_conflicts.py::test_at_10_conflicts_remain_separate`, `..._test_seam_has_no_conflict_resolution_api` | INV-06 | two envelopes, distinct ids/digests, no seam merge |
| AT-11 Observer cannot authorize | `test_observer.py::test_at_11_observer_cannot_authorize` | INV-01 | public API is exactly `{observe}` |
| AT-12 Observer cannot execute | `test_observer.py::test_at_12_observer_cannot_execute` | INV-09 | no execution terms in Observer source |
| AT-13 Authorized price separation | `test_ega_seam.py::test_at_13_authorized_price_is_outside_observer_evidence`; `validate_all.py` step | INV-04 | authorization context outside evidence tree, never imported by Observer |
| AT-14 Fixture source is read | `test_observer.py::test_at_14_value_is_read_through_source_interface`, `test_at_14_source_is_queried_for_the_observed_target` | INV-11 | output follows source content; source queried per observe |
| AT-15 Repeatability | `test_observer.py::test_at_15_repeatability_same_inputs_same_bytes`, `..._different_time_changes_evidence_id_and_digest`; `validate_all.py` determinism step | — | byte-identical regeneration |
| AT-16 EGA compatibility | `test_ega_seam.py::test_at_16_ega_compatibility_status_is_documented` | INV-12 | EGA unavailable → documentation records baseline commit + unavailability; test fails closed if repo appears without a probe |
| AT-17 Repository isolation | `test_invariants.py::test_at_17_no_writes_outside_project_root` | INV-11 | sandboxed generation with write guard passes |
| AT-18 Full suite | `validate_all.py` final step; full `pytest -q` run | all | 0 failed, 0 errors, 0 silently skipped |

## Invariant coverage (INV-01 .. INV-12)

See `tests/test_invariants.py`: each invariant has a dedicated test
(`test_inv_01_*` … `test_inv_12_*`). INV-02 additionally covered by the
catalog-hash stability test in `test_observer.py`
(`test_observation_does_not_mutate_catalog`).

## Corrective-pass regression tests

### Correction 1 — seam fail-closed validation (`tests/test_ega_seam.py`)

| Required regression | Test | Expected result |
|---|---|---|
| positive golden pass preserved | `test_seam_accepts_golden_envelope` | golden presented unchanged, digest verifies |
| missing required field | `test_seam_rejects_missing_required_field_even_with_recomputed_digest` | rejected by step 1 (schema) even though the digest is correct for the malformed payload |
| invalid `observed_state` | `test_seam_rejects_invalid_observed_state` (`"VERIFIED"`, recomputed digest) | rejected by step 1 |
| UNKNOWN with non-null value | `test_seam_rejects_unknown_state_with_non_null_value` (recomputed digest) | rejected by step 1 |
| KNOWN with null value | `test_seam_rejects_known_state_with_null_value` (recomputed digest) | rejected by step 1 |
| invalid `observed_at` | `test_seam_rejects_invalid_observed_at` (`"yesterday-ish"`, recomputed digest) | rejected by step 1 |
| forbidden authorization semantics | `test_seam_refuses_evidence_with_authorization_semantics` (nested inside `observed_value`, so schema-valid) | rejected by step 2 with "authorization semantics" |
| non-object input | `test_seam_rejects_non_object_input` | `TypeError` before validation |
| tampered digest (existing) | `test_seam_refuses_tampered_evidence` | rejected by step 3 (integrity) |

### Final hardening — semantic `observed_at` validation (`tests/test_ega_seam.py`)

The schema declares `"format": "date-time"` for `observed_at` in addition
to the canonical UTC-`Z` pattern, and `src/nextone_interop/validation.py`
attaches an active `jsonschema.FormatChecker` so the keyword is enforced.
Impossible calendar/time values must fail closed at step 1 (schema), before
integrity verification, even with a correctly recomputed digest.

| Required regression | Test | Expected result |
|---|---|---|
| impossible dates rejected | `test_seam_rejects_impossible_observed_at_even_with_recomputed_digest` (parametrized: `2026-02-30T12:00:00Z`, `2026-13-01T00:00:00Z`, `2026-10-03T25:00:00Z`, `2026-99-99T99:99:99Z`; all recomputed digests) | rejected by step 1 |
| non-leap-year Feb 29 rejected | `test_seam_rejects_non_leap_year_february_29` (`2026-02-29T12:00:00Z`, recomputed digest) | rejected by step 1 |
| leap-year Feb 29 accepted | `test_seam_accepts_leap_year_february_29` (`2024-02-29T12:00:00Z`, recomputed digest) | presented unchanged |
| golden timestamp positive | `test_seam_accepts_golden_observed_at_semantically` | golden `2026-10-03T19:00:00Z` stays valid under the active format check |
| malformed non-date string (existing) | `test_seam_rejects_invalid_observed_at` (`"yesterday-ish"`, recomputed digest) | rejected by step 1 |

### Final identity-hardening — `evidence_id` derivation consistency (`tests/test_ega_seam.py`)

The schema checks only the `ev1:<hex>` shape of `evidence_id`. The seam now
re-derives the expected id from the envelope identity fields with the same
authoritative `derive_evidence_id` as the Observer generation path and fails
closed on mismatch at pipeline step 2, before integrity verification. A
correctly recomputed digest must not rescue an identity mismatch.

| Required regression | Test | Expected result |
|---|---|---|
| wrong id + valid integrity | `test_seam_rejects_syntactically_valid_but_wrong_evidence_id` (`ev1:0000…0000`, recomputed digest) | rejected by step 2 with identity-consistency error; integrity not used to rescue |
| identity field changed, old id kept | `test_seam_rejects_stale_evidence_id_after_identity_field_change` (parametrized: `observed_value`, `provenance.source_id`, `observed_at`; integrity recomputed) | rejected by step 2 |
| provenance-only mutation | `test_seam_rejects_provenance_only_mutation_with_old_evidence_id` (`source_id` changed, integrity recomputed) | rejected by step 2 |
| golden positive (existing) | `test_seam_accepts_golden_envelope` | presented unchanged |
| same-time conflicts stay valid | `test_seam_same_timestamp_conflicts_remain_individually_valid` | same timestamp, different value/source: distinct ids, distinct digests, both pass seam validation individually |

### Correction 2 — evidence identity (`tests/test_evidence_identity.py`)

| Required regression | Test | Expected result |
|---|---|---|
| id format | `test_evidence_id_format_on_all_fixtures` | every fixture id matches `^ev1:[0-9a-f]{64}$` |
| same identity → same id | `test_same_identity_produces_same_id` | deterministic derivation |
| per-field sensitivity | `test_changing_any_identity_field_changes_id` (parametrized: subject, target, state, value, time, provenance `source_id`) | any change → different id |
| id ≠ integrity digest | `test_evidence_id_is_not_the_integrity_digest` | distinct inputs, distinct purposes |
| same-timestamp conflicts distinct | `test_same_timestamp_conflicting_observations_have_distinct_ids` | distinct ids and digests at identical `observed_at` |
| on-disk conflict independence | `test_on_disk_conflict_fixtures_retain_independent_ids_and_digests` | fixtures keep independent ids/digests/provenance |
| no accidental collisions | `test_all_fixtures_have_unique_evidence_ids` | all 6 fixture ids unique |

### Correction 3 — Observer clock (`tests/test_observer_clock.py`)

| Required regression | Test | Expected result |
|---|---|---|
| time captured from clock | `test_time_is_captured_from_the_injected_clock` | `observed_at` equals fixed clock time |
| default clock = system UTC | `test_default_clock_reads_system_utc` | timestamp within the observe call window, tz-aware |
| fixed clock deterministic | `test_fixed_clock_is_deterministic` | identical envelopes across observers |
| no timestamp parameter | `test_observe_signature_has_no_timestamp_parameter` | signature is exactly `{self, subject_type, tenant_id, resource, entity_id, field}` |
| arbitrary timestamps rejected | `test_caller_cannot_inject_an_arbitrary_timestamp` | `TypeError`; envelope still uses clock time |
| naive datetime rejected | `test_naive_datetime_is_rejected_by_fixed_clock`, `test_format_rfc3339_rejects_naive_datetimes` | `ValueError` |
| offset normalization | `test_offset_datetime_is_normalized_to_utc` | +02:00 → `Z` UTC form |
| microseconds | `test_microseconds_are_rendered_with_six_digits` | `.123456Z` |
| strict parsing | `test_parse_rfc3339_is_strict` | garbage, space-separated, offset-form, non-str all rejected |
| fixture determinism | `test_fixture_generation_remains_deterministic` | byte-identical regeneration |
| older observation generatable | `test_older_observation_fixture_is_intentionally_generatable` | older fixture builds with its explicit time, no FRESH/STALE |

## External compatibility classification

`test_at_16_ega_compatibility_status_is_documented` is the external
compatibility test. It cannot execute real compatibility because the EGA
repository is absent; by design it verifies the missing dependency is
documented instead of silently skipping, and it fails closed if a repository
appears at the baseline commit without a defined contract probe.

## Determinism

All fixture inputs are fixed (catalog snapshots, observation timestamps,
canonical JSON). No randomness, no wall-clock reads, no network. Regenerating
fixtures reproduces byte-identical files and digests.
