"""Security primitives: token generation, hashing, and constant-time comparison.

Authentication tokens are never stored in plaintext. We store only a SHA-256
digest, which is sufficient for a high-entropy random token (unlike a low-entropy
password, which would require a slow KDF). This keeps the database safe even if
it is leaked while keeping lookups fast.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_token(nbytes: int = 32) -> str:
    """Generate a URL-safe participant/API token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Hash a token for storage. Returns a hex digest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison to avoid timing side channels."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_token(token: str, stored_hash: str) -> bool:
    """Compare a presented token against a stored hash in constant time."""
    return constant_time_equals(hash_token(token), stored_hash)
