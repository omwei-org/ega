# EGA Reference Architecture

## End-to-end flow

```
Runtime AI Governance
        │
        │ runtime intent + governance context + evidence
        ▼
Vendor / System Adapter
        │
        ▼
Canonical Intent
        │
        ▼
Authorization Evaluation
        │
        ▼
Execution Authority
        │
        ▼
EABC
        │
        ▼
Enforcement Boundary
        │
        ├── BLOCK
        │
        └── COMMIT
              │
              ▼
            EFFECT
              │
              ▼
          Execution Evidence
```

## Architectural boundary

The key boundary is between **authorization** and **execution**.

EGA establishes explicit authority for an intended execution. It does not establish that the execution can be committed under every future runtime condition.

EABC and the downstream enforcement boundary independently evaluate the authority and current execution conditions before an effect is committed.

Therefore:

```
valid execution authority ≠ successful execution
```

## Authority without EGA

EGA is optional. EABC can consume execution authority from another authority source:

```
Authority Source → EABC → Enforcement Boundary → EFFECT
```

## Authority with EGA

```
Runtime AI Governance → EGA → EABC → Enforcement Boundary → EFFECT
```

## Material relevance

EGA is the architectural point at which the authorized execution scope and its relevant constraints are made explicit.

EABC does not infer why a particular condition is materially relevant. It verifies the conditions declared as part of the execution authority and applicable execution contract.

The enforcement boundary must then provide the properties required to enforce those conditions independently and without bypass.

## Example

A governance system produces:

```
intent:
  open valve V1 to 20%

authorization scope:
  V1
  open
  0–20%
  environment = plant-7
  validity = T
```

EGA issues explicit execution authority.

At PREPARE, EABC binds the authority to the execution context. At COMMIT, current conditions are checked again.

If a relevant execution condition changes:

```
PREPARE → state S1
          ↓
       state changes
          ↓
COMMIT → FINAL_AUTHORITY_CHECK = INVALID
          ↓
       NO EFFECT
```

If conditions remain valid, the execution boundary may commit and produce execution evidence.

## Relationship to EBP

EBP specifies required properties and conformance considerations for an execution boundary. It does not determine the authorization envelope and does not normatively select software or hardware as the enforcement substrate.
