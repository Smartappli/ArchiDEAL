"""Helpers for one-time URL tokens used by auth flows."""

from __future__ import annotations

import hashlib
import secrets

TOKEN_BYTES = 32
TOKEN_DIGEST_LENGTH = 64


def generate_url_token() -> str:
    """Return a high-entropy token safe for URL paths."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_url_token(token: str) -> str:
    """Return the database value for a one-time URL token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
