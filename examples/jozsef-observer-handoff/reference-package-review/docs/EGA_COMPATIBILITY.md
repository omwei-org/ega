# EGA Compatibility

## Target baseline

```text
Repository: EGA
Commit:     12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7
Description: Formalize Observer → EGA evidence adapter contract
```

## Availability in this workspace

The EGA repository at commit `12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7` is
**NOT available** in the workspace used to build this reference
(searched: workspace tree, Desktop `st observer` folder, and default sibling
paths; nothing found). No EGA source could be inspected.

## Was compatibility executed?

**No. Compatibility was NOT executed.** The exact EGA adapter contract at the
baseline commit was **not inspected** — no EGA interface was invented, no
fake compatibility results were produced, and no EGA source was created or
modified. Nothing in this document or in code claims that EGA accepts,
consumes, or understands the EvidenceEnvelope.

## Observer semantics to verify against the real EGA adapter

The seam in this reference (`src/nextone_interop/ega_seam.py`) presents the
EvidenceEnvelope losslessly: same fields, same values, same digest, after a
fail-closed validation pipeline (schema → semantic invariants, including forbidden semantics and `evidence_id` consistency → integrity → handoff). The following are **compatibility questions to be checked against
commit `12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7`** once the EGA repository is
available — they are statements about the Observer side only, not claims
about EGA behavior:

| EvidenceEnvelope v1 (Observer side, verified locally) | Compatibility question for the real EGA adapter | Status |
|---|---|---|
| `schema_version` = `nextone.observer.evidence-envelope/1.0` | Does the adapter recognize this evidence contract version, or require a different version identifier? | unverified |
| `subject` / `target` | Does the adapter accept this subject/target shape as its evaluation subject / resource pointer? | unverified |
| `observed_state` + `observed_value` | Does the adapter read the observed fact from exactly these fields? | unverified |
| `observed_at` + `temporal_basis` | Does the adapter treat this as temporal evidence and apply freshness at evaluation time? | unverified |
| `provenance` | Does the adapter accept this source-attribution shape? | unverified |
| `uncertainty` | Does the adapter accept this confidence slot? | unverified |
| `integrity` | Does the adapter verify integrity, and if so against which canonicalization? | unverified |

## Proposed seam representation pending EGA inspection

Until the EGA adapter contract is inspected, the only representation this
reference proposes is the EvidenceEnvelope v1 object itself, handed over
unchanged. Whether the real adapter consumes the object directly, maps
fields into its own structure, or requires a different evidence-only
representation is **unknown** and must be confirmed by inspecting EGA at the
baseline commit.

## Canonicalization status (validation refinement, section 7)

`nextone-canonical-json-v1` is the **standalone Observer-side**
canonicalization. It is used for the envelope integrity digest and for the
`evidence_id` identity payload. Its semantics were deliberately **not**
changed by the validation refinement.

EGA interoperability for the canonical representation is **not yet
established**: whether the real EGA adapter consumes the canonically
serialized object directly, maps fields before hashing, or applies different
canonicalization requirements is a compatibility question for Stanislav /
the EGA owners to confirm against the real adapter. No EGA-side
canonicalization behavior is assumed or speculated here.

## Mismatches

None recorded, because the EGA contract could not be inspected. If a future
compatibility run finds a mismatch, record here, for each item: Observer
field, EGA field as actually observed, semantic difference, syntactic vs
semantic, smallest possible future change, owning side. Do not change EGA to
make tests pass.

## No-change confirmation for EGA

No EGA source file was created, modified, patched, or deleted in this task.
Nothing in this project depends on EGA at runtime.

## Standalone side readiness

The standalone Observer side (schema, canonicalization, Observer with
clock-owned timestamps, strengthened `evidence_id`, fail-closed seam) is
implemented, tested, and documented, and is ready for Stanislav to inspect.
Compatibility itself remains **unverified** until run against the real EGA
adapter at the baseline commit.

## How to run the external compatibility test when EGA is available

1. Clone/checkout EGA at `12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7`.
2. Point `NEXTONE_EGA_REPO` at it (the test also probes sibling paths
   `ega/`, `nextone-ega/`, `EGA/`).
3. `pytest -q` — `test_at_16_ega_compatibility_status_is_documented` in
   `tests/test_ega_seam.py` currently fails closed if a repository is present
   but no contract probe is defined; extend that test (and this document)
   with the real contract checks instead of loosening the assertion.
