# ComOS operator issuer prototype

Status: prototype only. This issuer is not yet wired into the ComOS hub or node handler.

## Trust boundaries

- The issuer is a separate process and must be run by the operator, not imported into the node runtime.
- `COMOS_ISSUER_PRIVATE_KEY_B64` is the issuer's raw 32-byte Ed25519 private key encoded as base64. Do not provision it to the node runtime.
- `COMOS_HUB_ACT_PUBLIC_KEY_B64` is the hub's raw Ed25519 public key encoded as base64. The issuer requires an ACT signature made by the hub over canonical ACT JSON. Current ComOS ACTs do not yet provide this signed provenance, so issuance must remain unavailable until the hub signs the exact ACT and includes its `command_id`.
- `COMOS_ISSUER_SCOPE_JSON` is operator-owned policy, for example:

```json
{
  "allowed_tenants": ["tenant-vendor-1"],
  "allowed_products": ["p-1"],
  "allowed_principals": ["buyer-7"],
  "allowed_environments": ["test"],
  "max_quantity_per_item": 5,
  "max_total_coms": 1000
}
```

- `COMOS_ISSUER_TTL_SECONDS` defaults to 120 and is capped at 300.
- `EGA_SERVICE_AUDIENCE` must match the EGA service audience.
- `COMOS_ISSUER_AUTHORITY_ID` must match the authority ID mapped to the issuer public key in `EGA_AUTHORITY_PUBLIC_KEYS_JSON`.

## Request

`POST /v1/authority` receives the ACT, its hub signature, node-computed item unit prices and total, trusted principal, and environment. The issuer verifies hub provenance, validates the configured scope, verifies the pricing item/product alignment and arithmetic total, computes `comos-action-digest-v1`, and signs the EGA authority fields.

The issuer does not itself prove that node-reported prices came from an uncompromised catalog. The node must derive pricing from its trusted catalog, EGA's context provider must bind the context epoch to the catalog/product version, and the hub must continue its independent expected-price, payer-balance, and settlement checks.

## Still required before end-to-end use

1. Hub adds `command_id` and signs the exact ACT with its Ed25519 key.
2. Operator provisions the hub public key to the issuer and the issuer public key to EGA.
3. EGA installs a trusted `AUTHORITY_STATUS_PROVIDER`; signed-key mode intentionally fails closed without a revocation/status registry.
4. Node calls the issuer at execution time, then EGA, then consumes the permit atomically with the inventory reservation.
5. The ACT receipt echoes `command_id`, `action_digest`, and decision reference. Hub reconciles by command ID.
6. Integration tests prove scope denial, invalid hub signature, replay denial, expiry, tampered ACT, BLOCK with no reservation, and COMMIT with the same ACT/pricing snapshot.

This prototype does not guarantee complete mediation against a compromised node runtime that can bypass its own gate. Do not claim that guarantee without an isolated enforcement boundary.
