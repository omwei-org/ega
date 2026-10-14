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
`decision_record_digest`. This strict signed profile therefore requires EGA
issuance to be linked to a concrete decision record, even though the base
semantic model permits issuing an unsigned authority without one.

## Trust model

The private Ed25519 key must be held by a trusted EGA issuer service and used
only after that service has evaluated the intent and constructed the authority.
The consumer pins trusted public keys and an expected issuer. A signature proves
that the holder of the corresponding private key signed the claims; it does not
make an incorrectly operated issuer trustworthy.

The verifier also requires a trusted clock and a revocation provider. Revocation
provider failures, stale/unavailable data as reported by the provider, and
non-boolean results must be treated as failures. This module does not distribute
revocation data or prove that a provider's data is fresh; deployment must
provide that guarantee.

Install the optional dependency with `pip install -e '.[signed-authority]'`.
The profile is a reference cryptographic envelope, not a complete production
key-management, rotation, audit, or revocation service.
