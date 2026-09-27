# Minimal Run Trace

## ALLOW / COMMIT

```
RAIG
  → runtime intent: open valve-v1 to 20%
EGA
  → execution authority: VALID
EABC PREPARE
  → authority bound
EABC FINAL_AUTHORITY_CHECK
  → VALID
COMMIT
  → APPLIED
EFFECT
  → valve-v1 opened to 20%
```

## STALE / BLOCK

```
RAIG
  → runtime intent: open valve-v1 to 20%
EGA
  → execution authority: VALID
EABC PREPARE
  → authority bound at epoch 1
runtime state changes
  → epoch 2
EABC FINAL_AUTHORITY_CHECK
  → INVALID / STALE_CONTEXT
COMMIT
  → NOT_ATTEMPTED
EFFECT
  → NONE
```

The second trace demonstrates why execution authority does not itself constitute a commit permission.
