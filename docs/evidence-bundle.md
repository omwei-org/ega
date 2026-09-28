# EGA Evidence Bundle

## Status
Draft reference model. This document does **not** define a wire format, interoperability profile, or conformance requirement.

## Purpose
`ExecutionAttestation` (EAtt) records the outcome of an EGA/EABC boundary decision. It is intentionally smaller than a provenance or verification bundle.

An Evidence Bundle is a separate container for the evidence needed to independently correlate and reproduce that decision.

The distinction is:
- **EAtt** = execution-decision evidence record.
- **Evidence Bundle** = provenance and verification container around that record.

## Minimal correlation chain
```
Runtime Intent / Governance Evidence
              |
              v
      Authorization Authority
              |
              v
     PREPARE + Context Snapshot
              |
              v
   FINAL_AUTHORITY_CHECK
              |
              v
       COMMIT / BLOCK
              |
              v
             EAtt
              |
              v
    External Outcome Evidence*
```

`* External outcome evidence is optional at the EGA reference seam because this implementation does not perform or attest the external effect.`

## Identity separation
The following identities must not be conflated:
- **execution_id** — identity of the execution attempt/evidence record;
- **authority_id** — identity of the issued execution authority;
- **commit identity** — identity of the authoritative commit event, when such an identity exists;
- **external outcome identity** — identity of an independently evidenced external effect, when available.

An `execution_id` is therefore not treated as an EABC commit identifier.

## Content integrity
A future bundle format should support canonical serialization and content addressing so that an independent verifier can establish:
```
bundle inputs
    -> canonical representation
    -> digest
    -> independent verification
```

The verifier must verify declared evidence and bindings; it must not infer missing claims.

The `intent`, `authority`, `prepared_context`, `final_check`, `commit`, and `outcome` values in the current manifest are **opaque correlation references**. The reference implementation does not resolve them or prove that the referenced records exist. Their presence establishes a declared correlation handle only; independently verifiable lineage requires the referenced records and their integrity protection to be available to the verifier.

`manifest_sha256` is a deterministic content digest of the manifest as constructed by this reference implementation. It is not a signature, authentication mechanism, or proof that the referenced records or an external effect are authentic.

## Current implementation boundary
The current EGA implementation provides:
- deterministic authority issuance;
- PREPARE;
- final authority/context checking;
- COMMIT/BLOCK decision;
- EAtt generation;
- AO/AEE/ECT lineage references in EAtt.

It does not yet provide:
- a frozen Evidence Bundle wire format;
- signed/tamper-resistant EAtt;
- an authoritative commit-event identifier;
- independent proof of an external effect;
- an enforcement-boundary conformance mechanism.

These are intentionally separate from the semantic EGA reference implementation.

## Relation to EABC
EABC governs the execution-authority boundary semantics. The Evidence Bundle records the evidence needed to reconstruct and verify what happened at that boundary.

The bundle therefore supports EABC evidence correlation; it does not become a new execution-authority mechanism.
