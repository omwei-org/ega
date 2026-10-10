# Trusted Authority Status Provider Contract

Status: **integration contract; no production registry implementation is bundled**

## Purpose

Signature verification proves that an authority object was signed by a configured key. It does not prove that the authority remains active. In signed-authority mode, EGA calls `AUTHORITY_STATUS_PROVIDER` twice: before context/evidence evaluation and again immediately before returning its decision.

The provider receives a typed `AuthorityStatusQuery`, not the raw request. It includes `authority_id`, a SHA-256 `authority_digest` computed from the canonical authority payload (all fields except signature), nonce, source decision, validity interval, audience, and AO/AEE/ECT and decision-record references. It MUST determine status for that exact signed authority instance.

## Required provider behavior

The deployment-owned provider MUST:

1. At authority issuance/registration time, compute and persist the digest using the same canonicalization as signature verification: JSON with sorted keys, separators `,` and `:`, UTF-8, and all authority fields except `signature`.
2. At evaluation time, look up the registered record by both `authority_id` and the EGA-supplied `authority_digest`. Do not recompute a digest from the reduced query fields, and do not accept a digest copied from an untrusted caller field.
3. Return `True` only when that exact authority instance is registered as active and not revoked. Return `False` for revoked, unknown, superseded, or mismatched instances.
4. Fail by raising an exception when the registry is unavailable or cannot establish status. EGA returns HTTP 503; the provider must not translate an outage into `True`.
5. Use a registry with authenticated transport and access controls. A process-local dictionary or client-supplied `status` field is not a production revocation source.
6. Treat reissuance under a reused `authority_id` as a distinct instance. A different nonce, source decision, validity interval, or signed payload must not inherit the old instance's active status automatically.

## Decision semantics

- Provider returns `True`: continue other checks; this alone does not authorize COMMIT.
- Provider returns `False`: return `BLOCK / AUTHORITY_REVOKED` with `effect=NOT_EXECUTED`.
- Provider is absent in signed mode, fails, or returns a non-boolean: fail closed (HTTP 503).
- The two reads narrow the revocation window but are not atomic with one another or with a later ComOS effect. The execution boundary must independently enforce authority validity at the point of effect.

## Explicit non-claims

This contract is not a registry, signed revocation feed, key-management service, or ComOS adapter. It does not provide distributed consistency, atomic revocation, or global non-bypassability. No production integration should be claimed until a concrete provider and its trust assumptions are implemented and tested.
