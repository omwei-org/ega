# Signed EGA Execution Authority profile

This optional profile adds an authenticated artifact format around the EGA
reference model's `ExecutionAuthority`. Import it from
`ega.signed_authority`; the base `ega` package does not import the optional
cryptography dependency unless the signed profile is used. The plain dataclass and its digest are
not authentication: callers can construct or modify them.

## Profile

`ega-authority-ed25519-v1` signs a canonical JSON claims object containing:

- issuer and key ID;
- issue time, not-before, expiry, and unique JTI;
- the complete authority snapshot;
- a SHA-256 digest of that snapshot, including the source decision reference
  and the decision-record reference/digest.

The signer requires a non-empty `decision_record_ref` and
`decision_record_digest`. The preferred `issue_signed_authority()` entry point
calls EGA's `issue_authority()` first with a concrete `DecisionRecord`, so
scope evaluation and decision-record linkage happen before signing. The lower-
level `sign_authority()` function is for trusted integrations and must not be
exposed as an unguarded signing API.

## Trust model

The private Ed25519 key must be held by a trusted EGA issuer service and used
only after that service has evaluated the intent and constructed the authority.
The consumer pins trusted public keys and an expected issuer. A signature proves
that the holder of the corresponding private key signed the claims; it does not
make an incorrectly operated issuer trustworthy.

The verifier also requires a trusted clock, a revocation provider, and
authenticated resolvers for the canonical `DecisionRecord`, `RuntimeIntent`,
`AuthorizationScope`, and each referenced `EvidenceItem`. The decision record
must carry the exact intent and scope references and their canonical SHA-256
digests. The verifier resolves each object independently, checks references and
recomputed digests, re-runs EGA's scope evaluator against the resolved intent
and scope, and compares each embedded evidence item with its canonical resolved
counterpart before returning authority. AEE conditions must reference evidence
items actually present in the decision record; duplicate evidence references
are rejected. Missing objects, lookup errors, reference mismatch, digest mismatch,
evidence substitution, or out-of-scope parameters fail closed.

This proves that resolved object contents match their signed lineage digests,
that evidence records match their canonical resolved entries, and that the
runtime intent passes the resolved scope constraints. It does not independently
prove that upstream sensor claims are true, that the decision policy was correct,
or that the resolvers' stores are authoritative.
Those remain upstream provenance and deployment responsibilities.

Revocation provider failures, stale/unavailable data as reported by the provider,
and non-boolean results must be treated as failures. This module does not
distribute revocation data or prove that a provider's data is fresh; deployment
must provide that guarantee.

Install the optional dependency with `pip install -e '.[signed-authority]'`.
The profile is a reference cryptographic envelope, not a complete production
key-management, rotation, audit, or revocation service.
