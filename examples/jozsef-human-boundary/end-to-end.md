# End-to-End RAIG → EGA → EABC → EAtt Example

This example makes the EGA/SIF handoff concrete using the provider-neutral human-boundary scenario.

It uses the terminology of the public EGA/SIF implementation profile: **AO → AEE → ECT → EAtt**.

## 1. RAIG input to EGA

The upstream Runtime AI Governance layer provides governance-relevant runtime information. It does **not** issue the ECT.

Illustrative input:

```json
{
  "principal": "agent-123",
  "intent": {
    "action": "execute",
    "target": "task-001",
    "parameters": {
      "path": "A"
    }
  },
  "governance_context": {
    "decision_ref": "human-constraint-001",
    "instruction": "Use only execution path A; stop if unavailable"
  },
  "runtime_context": {
    "environment": "runtime-1",
    "context_epoch": 41
  },
  "evidence": {
    "source": "raig-1",
    "evidence_ref": "raig-event-991"
  }
}
```

This is governance input and runtime evidence. It is **not execution authority**.

## 2. DecisionRecord and AEE-condition projection

EGA preserves the evidence population considered for the authorization decision in an EGA-side `DecisionRecord`. The `DecisionRecord` is **not an EABC primitive** and does not mean that every upstream evidence item becomes a commit-time condition.

For example, the decision may consider:

```text
e-issuance
  evaluation_status = USED
  role              = issuance_basis
  digest            = sha256:issuance

e-observation
  evaluation_status = EVALUATED_NOT_USED
  role              = runtime_observation
  digest            = sha256:observation
```

The resulting authority retains the DecisionRecord reference and digest, but:

```text
aee_conditions = ()
aee_condition_digests = {}
```

Neither the issuance basis nor the evaluated-but-unused observation is automatically promoted to an AEE condition.

If EGA explicitly determines that a fact must remain true at commit time, it can project that fact into the minimal AEE-condition seam:

```text
e-freshness
  evaluation_status = USED
  role              = commit_condition
  digest            = sha256:freshness

→ aee_conditions = ("e-freshness",)
→ aee_condition_digests = {
     "e-freshness": "sha256:freshness"
  }
```

The distinction is therefore:

| EGA-side record | Commit semantics |
|---|---|
| `DecisionRecord` | preserves the full evidence population considered by EGA |
| `USED / issuance_basis` | explains issuance; not automatically a commit condition |
| `EVALUATED_NOT_USED` | remains decision evidence; not a commit condition |
| `USED / commit_condition` | explicitly projected into the AEE condition seam |
| `FINAL_AUTHORITY_CHECK` | checks the declared AEE conditions and current context; it does not interpret why RAIG evidence was considered |

This is a reference-implementation seam, not a complete AEE or evidence engine. In particular, freshness affects commit only when it is explicitly represented as a condition that must remain true at the execution boundary.

## 3. EGA evaluates against provisioning-time authorization

The applicable authorization scope is provisioned independently:

```text
principal = agent-123
action = execute
target = task-001
environment = runtime-1
path = A only
```

EGA evaluates the concrete runtime intent against that scope.

If it matches, the EGA/SIF profile represents the resulting authorization lineage as:

```
AO
 │
 ├─ decision_ref = human-constraint-001
 ├─ authorization_scope = path A only
 └─ governance context / decision references
      ↓
AEE
 │
 ├─ target = task-001
 ├─ execution constraint = path A
 ├─ environment = runtime-1
 ├─ context binding = epoch 41
 └─ lifecycle / correlation references
      ↓
ECT
 │
 ├─ authorized action = execute
 ├─ authorized path = A
 ├─ authority validity
 ├─ integrity protection
 └─ references to AO / AEE
```

Together, AO + AEE + ECT realize the portable authorization artifact described by the EGA/SIF profile.

## 4. PREPARE

The enforcement boundary receives the ECT and prepares the execution attempt against the current execution context.

At this point:

```text
ECT.path = A
context_epoch = 41
```

The agent may still have technical capability to reach another path. That capability does not modify the ECT or extend its authority.

## 5. Runtime change before COMMIT

Before commit, path A becomes unavailable.

The runtime execution context advances:

```text
context_epoch: 41 → 42
```

Path B may be technically available.

That does **not** transform:

```text
ECT(path A)
```

into:

```text
ECT(path B)
```

The prepared authority is now stale relative to the execution context.

## 6. FINAL_AUTHORITY_CHECK

The execution boundary re-evaluates the prepared authority against current conditions.

```text
prepared_epoch = 41
current_epoch  = 42

→ STALE_CONTEXT
→ INVALID for commit
```

Therefore:

```text
COMMIT NOT ATTEMPTED
EFFECT = NONE
```

The substitute path is not executed merely because it is technically available.

## 7. EAtt

For a blocked attempt, the public EGA/SIF profile requires failure to remain distinguishable from successful execution. A deployment-specific EAtt/failure record can preserve:

```text
execution_id
ECT reference
AO / AEE correlation
prepared context
current context
final check = INVALID
reason = STALE_CONTEXT
commit = NOT_ATTEMPTED
effect = NONE
```

For a successful execution, EAtt instead binds the ECT, commit event, and execution outcome.

## 8. What this demonstrates

The end-to-end evidence chain becomes:

```
RAIG evidence
    ↓
DecisionRecord
    ↓
AO
    ↓
AEE
    ↓
ECT
    ↓
PREPARE
    ↓
current execution state
    ↓
FINAL_AUTHORITY_CHECK
    ↓
COMMIT / BLOCK
    ↓
EAtt / failure evidence
```

This provides the bridge Jozsef identified between **runtime evidence before consequence** and **reconstruction after consequence**.

The example does not claim that EGA or this Python reference implementation itself provides tamper-resistant enforcement. Enforcement-boundary properties and implementation conformance remain separate concerns.
