# Human Boundary / Substituted Execution Path

This example models a runtime-control failure in which a human instruction restricts the execution path and the agent has a technically available substitute path.

The scenario is intentionally provider-neutral. It demonstrates the distinction between capability and execution authority.

## Scenario

Human instruction:

> Use only execution path A. If that is not possible, stop rather than continue another way.

Runtime governance provides the intent and governance context to EGA. The provisioning-time authorization scope permits only path A.

EGA issues execution authority for path A. Path B may remain technically callable, but it is outside the issued execution authority.

If path A becomes unavailable after PREPARE, the execution boundary must not silently substitute path B.

## Flow

```
Human constraint
      ↓
Runtime AI Governance
      ↓ runtime intent + governance context + evidence
EGA
      ↓ ExecutionAuthority(path A)
EABC PREPARE
      ↓
path A becomes unavailable
      ↓
agent can technically reach path B
      ↓
FINAL_AUTHORITY_CHECK
      ↓
BLOCK / COMMIT NOT ATTEMPTED
      ↓
NO EFFECT
```

## Key invariant

```
capability(path B) ≠ authority(path B)
```

The ability to execute a substitute path is not evidence that the substitute path is authorized.

A valid authority artifact is necessary but not sufficient for commit: the current execution conditions must still satisfy the boundary contract.

## Evidence

A conforming implementation should be able to correlate at least:

- the governance decision / human constraint;
- the issued execution authority;
- the PREPARE context;
- the current execution condition that invalidated the prepared authority;
- the final authority-check result;
- the commit result;
- the absence or presence of an externally observable effect.

This example does not implement an external effect. The boundary seam remains responsible for the commit decision; the downstream enforcement implementation is deployment-specific.
