# EGA Decision Evidence

## Status

Reference implementation model. This document defines an EGA-side decision-record pattern; it is not an EABC Core primitive and does not define a wire format or conformance requirement.

## Purpose

EGA must preserve enough decision evidence to reconstruct why execution authority was issued without carrying the full upstream RAIG evidence population through the execution contract.

The model separates four evidence roles:

1. **considered** — evidence available to EGA during the authority decision;
2. **used for issuance** — evidence materially relied upon to issue authority;
3. **promoted to AEE** — resulting conditions that must still hold at commit;
4. **observed at the boundary** — evidence establishing whether those conditions still held when consequence was attempted.

## Decision Record

A `DecisionRecord` is an EGA-side provenance record containing:

- decision identifier and decision time;
- reference to the runtime intent;
- reference to the applicable authorization scope;
- references and digests for the evidence items considered by EGA;
- evaluation status for each item;
- optional role describing how EGA used or classified the item;
- source-reported confidence, when supplied.

The record does not assert that upstream evidence is true. In particular, confidence is retained as a value reported by the source, not as an EGA or EABC guarantee.

An evidence item may be retained as `EVALUATED_NOT_USED`, for example when it was stale, insufficiently trusted, superseded, or non-material to the authority decision.

## Authority and commit boundary

The lineage is:

```
RAIG evidence population
        |
        v
EGA Decision Record
        |
        | decision reference
        v
       AO
        |
        v
      AEE / ECT
        |
        v
FINAL_AUTHORITY_CHECK
        |
        v
      EAtt
```

The Decision Record explains why authority was issued.

AEE contains only conditions that must remain true at commit. Evidence freshness becomes a commit-time concern only when the resulting freshness/validity requirement is explicitly represented as an AEE condition.

## EAtt lineage

EAtt references the Decision Record as the primary explanation of authority issuance.

EAtt may additionally carry selected direct evidence references when a particular evidence item materially explains the final boundary outcome, for example when a freshness state, authority condition, or runtime observation changed between issuance and commit and directly caused COMMIT or BLOCK.

This is selective lineage, not propagation of the full RAIG evidence population through EABC.

## Integrity

Where a conforming implementation provides integrity protection, the Decision Record reference, digest, and selected evidence references must be protected as part of the EAtt correlation. External unprotected mappings must not be required to reconstruct the lineage.

The current Python implementation is semantic/reference code and does not provide tamper-resistant attestation or independent proof of external effects.
