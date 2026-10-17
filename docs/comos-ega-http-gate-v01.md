# ComOS → EGA HTTP gate integration contract (v0.1)

## Install

Install the adapter dependency with `pip install -e ".[comos]"` from this repository. Install the EGA service dependencies separately with `pip install -e ".[service]"`.

## Insertion point

The ComOS-side caller must invoke `EGAHTTPGate.authorize_before_effect(...)` before the first protected effect in the relevant action path. The integration audit identified `routeToolCall` and `beginPerActCharge` as the location to validate with Ron. The gate must precede charging, enqueueing, order creation, or any other protected effect.

## Request contract

The adapter sends `POST /v1/evaluate` with the shape `{intent, authority, context_epoch}`. The intent must satisfy EGA's `RuntimeIntentRequest` schema (`principal`, `action`, `target`, `parameters.items`, `environment`, plus optional context/evidence fields); authority must satisfy EGA's `ExecutionAuthorityRequest` schema. Observer v1 envelopes are passed as `intent.evidence_envelopes`, not as an unrelated top-level field.

## Required caller behavior

1. Derive runtime intent from the exact action and parameters ComOS is about to execute; do not authorize a separate or caller-controlled intent unrelated to the execution payload.
2. Supply the pre-existing authority and a trusted current `context_epoch`; do not take the trusted epoch from an untrusted request.
3. Call EGA over the configured service endpoint.
4. Proceed only on HTTP success plus a well-formed response with `decision == "COMMIT"`, `applied is True`, a non-empty `reason`, and `effect` in `NONE` or `NOT_EXECUTED`.
5. Treat BLOCK, missing authority, timeout, connection failure, HTTP error, malformed response, and unknown response shape as denial.
6. Execute exactly the parameters covered by the authorized intent. Any mutation after authorization requires re-authorization.

## What this provides

The Python adapter is a real HTTP client for EGA's `POST /v1/evaluate` endpoint and has tests for transport failures, malformed responses, explicit BLOCK, and callback suppression on denial.

## Enforcement boundary

This repository-only adapter cannot force a closed-source or inaccessible ComOS runtime to call it. End-to-end enforcement is established only when the ComOS owner inserts the call in the real action path and tests prove that no protected effect occurs on denial. The adapter is not an SLC and does not eliminate races between EGA's decision and an external effect unless the execution boundary binds the checked payload and state to the effect.

## Deployment warning

Run the EGA service with signed-authority verification, a trusted authority-status provider, a trusted context-version provider, persistent replay protection, and appropriate transport/authentication controls. Do not enable `EGA_ALLOW_UNVERIFIED_AUTHORITY` for real traffic.
