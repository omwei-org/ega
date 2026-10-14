"""Authenticated EGA ExecutionAuthority envelope.

This optional profile signs an authority snapshot plus its decision-record
reference/digest. The signing key must be held by the trusted EGA issuer
service; possession of an ExecutionAuthority dataclass alone is not proof.
"""
from __future__ import annotations

import base64
import json
import math
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .evidence import decision_record_digest
from .models import DecisionRecord, ExecutionAuthority


class AuthorityEnvelopeError(ValueError):
    """Raised when an authenticated EGA authority cannot be verified."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthorityEnvelopeError("value is not canonical-JSON serializable") from exc


def _authority_mapping(authority: ExecutionAuthority | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(authority, ExecutionAuthority):
        value = asdict(authority)
    elif isinstance(authority, Mapping):
        value = dict(authority)
    else:
        raise AuthorityEnvelopeError("authority must be an ExecutionAuthority or mapping")
    required = (
        "authority_id", "principal", "action", "target", "parameters",
        "environment", "source_decision", "status",
        "decision_record_ref", "decision_record_digest",
    )
    if any(field not in value for field in required):
        raise AuthorityEnvelopeError("authority is missing required identity or decision lineage")
    for field in (
        "authority_id", "principal", "action", "target", "environment",
        "source_decision", "decision_record_ref", "decision_record_digest",
    ):
        if not isinstance(value[field], str) or not value[field].strip():
            raise AuthorityEnvelopeError(f"authority.{field} must be a non-empty string")
    if value["status"] != "VALID":
        raise AuthorityEnvelopeError("authority status is not VALID")
    if not isinstance(value["parameters"], Mapping):
        raise AuthorityEnvelopeError("authority.parameters must be an object")
    return value


def sign_authority(
    authority: ExecutionAuthority | Mapping[str, Any],
    *,
    private_key: Ed25519PrivateKey,
    issuer: str,
    key_id: str,
    issued_at: int,
    not_before: int,
    expires_at: int,
    jti: str,
) -> bytes:
    """Sign an authority only at the trusted EGA issuer boundary.

    The authority must carry a source decision reference and digest of the
    corresponding decision record. This function cannot protect a private key
    that is exposed to untrusted callers.
    """
    if not all(isinstance(v, str) and v.strip() for v in (issuer, key_id, jti)):
        raise AuthorityEnvelopeError("issuer, key_id, and jti are required")
    for name, value in (
        ("issued_at", issued_at), ("not_before", not_before), ("expires_at", expires_at)
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AuthorityEnvelopeError(f"{name} must be a non-negative integer")
    if not (issued_at <= not_before < expires_at):
        raise AuthorityEnvelopeError("validity interval must satisfy issued_at <= not_before < expires_at")

    value = _authority_mapping(authority)
    claims = {
        "schema": "ega-authority-ed25519-v1",
        "issuer": issuer,
        "key_id": key_id,
        "issued_at": issued_at,
        "not_before": not_before,
        "expires_at": expires_at,
        "jti": jti,
        "authority": value,
        "authority_sha256": sha256(_canonical_json(value)).hexdigest(),
    }
    signature = private_key.sign(_canonical_json(claims))
    return _canonical_json({
        "claims": claims,
        "signature": base64.b64encode(signature).decode("ascii"),
    })


def verify_signed_authority(
    artifact: bytes,
    *,
    trusted_keys: Mapping[str, Ed25519PublicKey],
    expected_issuer: str,
    now: int,
    is_revoked: Callable[[str], bool],
    decision_record_resolver: Callable[[str], DecisionRecord] | None = None,
) -> dict[str, Any]:
    """Verify origin, integrity, decision-record content, time bounds, and revocation.

    Both revocation and decision-record resolution are mandatory trusted
    dependencies. The resolver must retrieve the record from an authenticated
    source by reference. The verifier recomputes its digest; a signed reference
    alone is not proof that the referenced record exists or has the claimed content.
    Providers that fail or return unexpected values fail closed.
    """
    if not isinstance(expected_issuer, str) or not expected_issuer:
        raise AuthorityEnvelopeError("trusted expected_issuer is required")
    if isinstance(now, bool) or not isinstance(now, int) or now < 0:
        raise AuthorityEnvelopeError("trusted current time is required")
    if not callable(is_revoked):
        raise AuthorityEnvelopeError("trusted revocation provider is required")
    if not callable(decision_record_resolver):
        raise AuthorityEnvelopeError("trusted decision-record resolver is required")
    try:
        envelope = json.loads(artifact.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorityEnvelopeError("authority artifact is not valid UTF-8 JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"claims", "signature"}:
        raise AuthorityEnvelopeError("invalid authority envelope")
    claims = envelope["claims"]
    if not isinstance(claims, dict) or claims.get("schema") != "ega-authority-ed25519-v1":
        raise AuthorityEnvelopeError("unsupported authority envelope schema")
    issuer, key_id, jti = claims.get("issuer"), claims.get("key_id"), claims.get("jti")
    if not all(isinstance(v, str) and v for v in (issuer, key_id, jti)):
        raise AuthorityEnvelopeError("issuer, key_id, and jti are required")
    if issuer != expected_issuer:
        raise AuthorityEnvelopeError("authority issuer is not trusted")
    public_key = trusted_keys.get(key_id)
    if public_key is None:
        raise AuthorityEnvelopeError("authority signing key is not trusted")
    signature_text = envelope["signature"]
    if not isinstance(signature_text, str):
        raise AuthorityEnvelopeError("signature must be base64 text")
    try:
        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(signature, _canonical_json(claims))
    except (ValueError, InvalidSignature) as exc:
        raise AuthorityEnvelopeError("authority signature verification failed") from exc

    issued_at, not_before, expires_at = (
        claims.get("issued_at"), claims.get("not_before"), claims.get("expires_at")
    )
    for name, value in (
        ("issued_at", issued_at), ("not_before", not_before), ("expires_at", expires_at)
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AuthorityEnvelopeError(f"{name} is invalid")
    if not (issued_at <= not_before < expires_at):
        raise AuthorityEnvelopeError("authority validity interval is invalid")
    if now < not_before or now >= expires_at:
        raise AuthorityEnvelopeError("authority is not currently valid")

    try:
        revoked = is_revoked(jti)
    except Exception as exc:
        raise AuthorityEnvelopeError("authority revocation check failed") from exc
    if revoked is True:
        raise AuthorityEnvelopeError("authority has been revoked")
    if revoked is not False:
        raise AuthorityEnvelopeError("authority revocation provider returned a non-boolean result")

    authority = claims.get("authority")
    if not isinstance(authority, dict):
        raise AuthorityEnvelopeError("signed authority payload must be an object")
    if sha256(_canonical_json(authority)).hexdigest() != claims.get("authority_sha256"):
        raise AuthorityEnvelopeError("authority digest mismatch")
    normalized = _authority_mapping(authority)
    record_ref = normalized["decision_record_ref"]
    if normalized["source_decision"] != record_ref:
        raise AuthorityEnvelopeError("source decision does not match decision-record reference")
    try:
        record = decision_record_resolver(record_ref)
    except Exception as exc:
        raise AuthorityEnvelopeError("decision-record resolution failed") from exc
    if not isinstance(record, DecisionRecord):
        raise AuthorityEnvelopeError("decision-record resolver returned an invalid record")
    if record.decision_id != record_ref:
        raise AuthorityEnvelopeError("resolved decision-record ID does not match signed reference")
    if not record.authorization_scope_ref or not record.intent_ref:
        raise AuthorityEnvelopeError("resolved decision record has incomplete lineage")
    try:
        actual_record_digest = decision_record_digest(record)
    except Exception as exc:
        raise AuthorityEnvelopeError("decision-record digest computation failed") from exc
    if actual_record_digest != normalized["decision_record_digest"]:
        raise AuthorityEnvelopeError("decision-record digest mismatch")
    return normalized


def issue_signed_authority(
    intent: Any,
    scope: Any,
    *,
    decision_record: Any,
    private_key: Ed25519PrivateKey,
    issuer: str,
    key_id: str,
    issued_at: int,
    not_before: int,
    expires_at: int,
    jti: str,
    authority_id: str = "ega-authority-001",
) -> bytes:
    """Evaluate scope and bind a decision record before signing the authority.

    This is the preferred issuer entry point: it calls EGA's own
    `issue_authority` function rather than signing an arbitrary caller-created
    authority object. The decision record and authorization scope must still
    originate from trusted upstream/provisioning services.
    """
    from .authority import issue_authority
    from .models import DecisionRecord, RuntimeIntent, AuthorizationScope

    if not isinstance(intent, RuntimeIntent):
        raise AuthorityEnvelopeError("intent must be an EGA RuntimeIntent")
    if not isinstance(scope, AuthorizationScope):
        raise AuthorityEnvelopeError("scope must be an EGA AuthorizationScope")
    if not isinstance(decision_record, DecisionRecord):
        raise AuthorityEnvelopeError("a concrete EGA DecisionRecord is required")
    authority = issue_authority(
        intent,
        scope,
        authority_id=authority_id,
        decision_record=decision_record,
    )
    return sign_authority(
        authority,
        private_key=private_key,
        issuer=issuer,
        key_id=key_id,
        issued_at=issued_at,
        not_before=not_before,
        expires_at=expires_at,
        jti=jti,
    )
