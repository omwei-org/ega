# Minimal EGA → EABC Flow

This example demonstrates the separation between governance input, execution authority, and commit.

## Flow

```
RAIG input
   ↓
EGA
   ↓
Execution Authority
   ↓
EABC
   ↓
COMMIT or BLOCK
   ↓
EFFECT
```

The example is intentionally implementation-neutral and deterministic.

## Scenario

A Runtime AI Governance system produces an intent to open valve V1 to 20%.

EGA evaluates that intent against an applicable authorization scope and issues bounded execution authority.

Two outcomes are illustrated:

1. current execution conditions remain valid → COMMIT → EFFECT;
2. a relevant condition changes after PREPARE → FINAL_AUTHORITY_CHECK fails → no effect.

The key invariant is:

```
valid authority ≠ valid commit
```
