#!/usr/bin/env python3
"""Validate the production Valkey Secret without printing its value."""

from __future__ import annotations

import argparse
import base64
import binascii
import sys
from urllib.parse import urlsplit


class ValkeyURLValidationError(ValueError):
    """Raised when the production Valkey URL violates the runtime contract."""


def validate_valkey_url(value: str, *, expected_host: str) -> None:
    if not value or value != value.strip() or any(character.isspace() for character in value):
        raise ValkeyURLValidationError("Valkey URL is empty or contains whitespace.")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValkeyURLValidationError("Valkey URL is malformed.") from exc
    if parsed.scheme.lower() != "rediss":
        raise ValkeyURLValidationError("Valkey URL must use rediss://.")
    if not hostname or hostname.casefold() != expected_host.casefold():
        raise ValkeyURLValidationError(
            "Valkey URL hostname does not match the approved VALKEY_HOST."
        )
    if port != 6380:
        raise ValkeyURLValidationError("Valkey URL must use the TLS port 6380.")
    if not parsed.password:
        raise ValkeyURLValidationError("Valkey URL must contain an ACL password.")
    if not parsed.path.startswith("/") or not parsed.path[1:].isdigit():
        raise ValkeyURLValidationError("Valkey URL must select a numeric database.")
    if parsed.query:
        raise ValkeyURLValidationError(
            "Valkey URL query options are forbidden because they can weaken TLS verification."
        )
    if parsed.fragment:
        raise ValkeyURLValidationError("Valkey URL must not contain a fragment.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-host", required=True)
    args = parser.parse_args()

    try:
        encoded = sys.stdin.buffer.read()
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        validate_valkey_url(decoded, expected_host=args.expected_host)
    except (binascii.Error, UnicodeDecodeError):
        print("Valkey Secret is not valid base64-encoded UTF-8.", file=sys.stderr)
        return 2
    except ValkeyURLValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Valkey TLS Secret contract validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
