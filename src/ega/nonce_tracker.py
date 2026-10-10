"""
Nonce tracker for replay protection.

For production, use a persistent store (Redis, database, etc.).
This implementation uses in-memory storage for testing.
"""

import threading
from typing import Set


class NonceTracker:
    """
    In-memory nonce tracker with thread-safe consumption.

    For production, replace with Redis or database-backed implementation.
    """

    def __init__(self):
        self.consumed_nonces: Set[str] = set()
        self.lock = threading.Lock()

    def consume(self, authority_id: str, nonce: str) -> bool:
        """
        Atomically consume a nonce if not already used.

        Args:
            authority_id: Authority identifier
            nonce: Nonce to consume

        Returns:
            True if nonce was consumed (first use), False if already used
        """
        key = f"{authority_id}:{nonce}"

        with self.lock:
            if key in self.consumed_nonces:
                return False
            self.consumed_nonces.add(key)
            return True

    def is_consumed(self, authority_id: str, nonce: str) -> bool:
        """
        Check if a nonce has been consumed.

        Args:
            authority_id: Authority identifier
            nonce: Nonce to check

        Returns:
            True if nonce is already consumed, False otherwise
        """
        key = f"{authority_id}:{nonce}"
        with self.lock:
            return key in self.consumed_nonces

    def reset(self) -> None:
        """Reset all consumed nonces (for testing only)."""
        with self.lock:
            self.consumed_nonces.clear()

    def count(self) -> int:
        """Return the number of consumed nonces (for testing)."""
        with self.lock:
            return len(self.consumed_nonces)


# Global nonce tracker instance
_global_nonce_tracker: NonceTracker = None
_global_nonce_tracker_lock = threading.Lock()


def get_nonce_tracker() -> NonceTracker:
    """
    Get the global nonce tracker instance.

    Returns:
        NonceTracker instance
    """
    global _global_nonce_tracker

    with _global_nonce_tracker_lock:
        if _global_nonce_tracker is None:
            _global_nonce_tracker = NonceTracker()

    return _global_nonce_tracker


def reset_nonce_tracker() -> None:
    """Reset the global nonce tracker (for testing only)."""
    global _global_nonce_tracker

    with _global_nonce_tracker_lock:
        if _global_nonce_tracker is not None:
            _global_nonce_tracker.reset()
