# Minimal Flow

## 1. RAIG → EGA

The input contains runtime intent, governance context, identity, and provenance.

## 2. EGA → Execution Authority

EGA transforms the input into bounded execution authority:

- principal = agent-123
- action = open
- target = valve-v1
- value = 0–20%
- environment = plant-7
- source decision = raig-decision-784

## 3. EABC PREPARE

The authority is bound to the current execution context.

## 4. COMMIT

If the declared execution conditions remain valid, the execution boundary may commit.

If a relevant condition changes between PREPARE and COMMIT:

```
FINAL_AUTHORITY_CHECK = INVALID
COMMIT = NOT_ATTEMPTED
EFFECT = NONE
```

## 5. Evidence

The resulting execution evidence correlates the authority, commit decision, and execution outcome.
