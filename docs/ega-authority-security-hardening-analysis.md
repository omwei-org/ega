# EGA Authority Security — Verified Service Contract

**Reviewed:** 2026-10-10  
**Scope:** Existing `fix/ega-service-security-v01` service implementation, as carried into the ComOS integration test branch.  
**Purpose:** Record verified behavior and deployment constraints. This is not a proposed implementation plan.

## Verified service behavior

The HTTP service in `src/ega/service.py` evaluates a pre-existing authority; it does not issue authority.

In signed-authority mode, the service:

1. Loads Ed25519 public keys from `EGA_AUTHORITY_PUBLIC_KEYS_JSON`, keyed by authority ID.
2. Requires a signature and verifies it over canonical JSON of the authority request, excluding only the `signature` field.
3. Requires a nonce, timezone-aware issue/expiry timestamps, a matching `EGA_SERVICE_AUDIENCE`, a valid time window, and a lifetime no longer than `EGA_MAX_AUTHORITY_TTL_SECONDS`.
4. Requires a configured trusted authority-status provider and blocks an authority reported inactive.
5. Checks that runtime intent matches the authority's principal, action, target, environment, and parameters.
6. Requires a trusted context-version provider, compares the supplied context version with trusted state, and rechecks the context before final authority checking.
7. Converts Observer v1 evidence envelopes through the existing adapter and rejects stale or invalid evidence.
8. Claims the authority nonce in a SQLite replay ledger. The ledger uses an atomic transaction and rejects duplicate `(authority_id, nonce)` pairs.

The default configuration fails closed when verification keys or the trusted context provider are missing. `EGA_ALLOW_UNVERIFIED_AUTHORITY=true` is an explicitly unsafe test/demo bypass; it must not be enabled for production traffic.

## Deployment limitations

- The SQLite replay ledger protects workers sharing the same database file on one host. It is not a distributed replay defense for multi-host deployments; use a shared strongly consistent store before deploying that way.
- Trusted public keys, authority status, and current context state must be provisioned by trusted deployment components. The repository does not supply a production authority registry or context provider.
- The service source notes that HTTP authentication is not implemented; network access must be protected by an appropriate security layer.
- Signature verification authenticates the signed authority payload. It does not itself prove that a downstream executor enforces the EABC/SLC contract or that a real-world effect occurred.

## Integration test boundaries

- `tests/test_comos_ega_service_integration.py` starts a real local HTTP service subprocess. Its test configuration enables the unsafe unsigned-authority bypass only inside that subprocess and injects a fixed test context provider. These tests validate HTTP behavior; they do not validate production key provisioning.
- `tests/test_comos_ega_harness.py` is a simulated adapter harness. Its simulated effects are not proof of ComOS enforcement.
- `tests/test_comos_ega_integration.py` and `tests/test_state_drift_experiment.py` use the local ComOS endpoint at `127.0.0.1:9101` and can create or change test catalog data. They now require explicit opt-in with `EGA_RUN_LIVE_COMOS=1`. Run them only against a disposable/test ComOS tenant and inspect their output; they are not safe to run against a production tenant.
- A passing harness or experiment does not establish SLC enforcement. The live ComOS tests exercise an experimental gate and simulated evidence, not a production EABC/SLC implementation or a real Observer integration.

## CI status

The GitHub Actions suite passed **153 tests with 3 skips** before the live-test opt-in change. Re-check the latest run for the current branch head before treating that result as final.
