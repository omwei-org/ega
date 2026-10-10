"""
Cryptographic utilities for EGA authority signing and verification.

Uses Ed25519 for digital signatures.
"""

import base64
import hashlib
from typing import Dict, Optional
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


class SignatureError(Exception):
    """Raised when signature verification fails."""
    pass


class KeyError(Exception):
    """Raised when key operations fail."""
    pass


def generate_ed25519_keypair() -> tuple[str, str]:
    """
    Generate a new Ed25519 keypair.

    Returns:
        (private_key_b64, public_key_b64) - Base64-encoded keys
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Encode as base64
    private_key_b64 = base64.b64encode(
        private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    ).decode('utf-8')

    public_key_b64 = base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    ).decode('utf-8')

    return private_key_b64, public_key_b64


def load_private_key(private_key_b64: str) -> ed25519.Ed25519PrivateKey:
    """
    Load Ed25519 private key from base64.

    Args:
        private_key_b64: Base64-encoded private key

    Returns:
        Ed25519PrivateKey instance
    """
    try:
        private_key_bytes = base64.b64decode(private_key_b64)
        return ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    except Exception as e:
        raise KeyError(f"Failed to load private key: {e}")


def load_public_key(public_key_b64: str) -> ed25519.Ed25519PublicKey:
    """
    Load Ed25519 public key from base64.

    Args:
        public_key_b64: Base64-encoded public key

    Returns:
        Ed25519PublicKey instance
    """
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        return ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
    except Exception as e:
        raise KeyError(f"Failed to load public key: {e}")


def sign(private_key: ed25519.Ed25519PrivateKey, message: bytes) -> str:
    """
    Sign a message using Ed25519.

    Args:
        private_key: Ed25519 private key
        message: Message to sign (bytes)

    Returns:
        Base64-encoded signature
    """
    signature = private_key.sign(message)
    return base64.b64encode(signature).decode('utf-8')


def verify(public_key: ed25519.Ed25519PublicKey, message: bytes, signature_b64: str) -> bool:
    """
    Verify a signature using Ed25519.

    Args:
        public_key: Ed25519 public key
        message: Original message (bytes)
        signature_b64: Base64-encoded signature

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, message)
        return True
    except Exception:
        return False


class KeyStore:
    """
    In-memory store of trusted public keys.

    For production, use a persistent store (database, Redis, etc.).
    """

    def __init__(self):
        self.keys: Dict[str, ed25519.Ed25519PublicKey] = {}

    def add_key(self, key_id: str, public_key_b64: str) -> None:
        """Add a trusted public key."""
        public_key = load_public_key(public_key_b64)
        self.keys[key_id] = public_key

    def get_key(self, key_id: str) -> Optional[ed25519.Ed25519PublicKey]:
        """Get a trusted public key by ID."""
        return self.keys.get(key_id)

    def has_key(self, key_id: str) -> bool:
        """Check if a key ID is trusted."""
        return key_id in self.keys

    def load_from_env(self, env_var: str = "EGA_TRUSTED_PUBLIC_KEYS") -> None:
        """
        Load trusted keys from environment variable.

        Expected format: JSON object mapping key_id -> base64 public key
        Example: '{"key-001": "BASE64_PUBLIC_KEY", "key-002": "BASE64_PUBLIC_KEY"}'
        """
        import os
        import json

        keys_json = os.getenv(env_var, "")
        if not keys_json:
            return

        try:
            keys_dict = json.loads(keys_json)
            for key_id, public_key_b64 in keys_dict.items():
                self.add_key(key_id, public_key_b64)
        except Exception as e:
            raise KeyError(f"Failed to load keys from {env_var}: {e}")
