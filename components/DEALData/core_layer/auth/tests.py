"""Tests for authentication helpers."""

from unittest import TestCase

from django.test import RequestFactory

from auth.redirects import get_safe_next_url
from auth.tokens import TOKEN_DIGEST_LENGTH, generate_url_token, hash_url_token

CHECK = TestCase()


def test_generate_url_token_returns_distinct_url_safe_tokens() -> None:
    """Generated URL tokens are unique and safe to place in URLs."""
    first_token = generate_url_token()
    second_token = generate_url_token()

    CHECK.assertNotEqual(first_token, second_token)
    CHECK.assertNotIn("/", first_token)
    CHECK.assertNotIn("+", first_token)
    CHECK.assertNotIn("=", first_token)


def test_hash_url_token_is_stable_and_does_not_store_plaintext() -> None:
    """Token hashing is deterministic and does not keep the plain token."""
    token = generate_url_token()

    first_digest = hash_url_token(token)
    second_digest = hash_url_token(token)

    CHECK.assertEqual(first_digest, second_digest)
    CHECK.assertNotEqual(first_digest, token)
    CHECK.assertEqual(len(first_digest), TOKEN_DIGEST_LENGTH)


def test_get_safe_next_url_accepts_relative_paths() -> None:
    """Relative post-login redirect targets are accepted."""
    request = RequestFactory().post("/login/", {"next": "/projects/"})

    CHECK.assertEqual(get_safe_next_url(request), "/projects/")


def test_get_safe_next_url_rejects_external_hosts(settings) -> None:
    """External post-login redirect targets are rejected."""
    settings.ALLOWED_HOSTS = ["*"]
    request = RequestFactory().post(
        "/login/",
        {"next": "https://example.invalid/projects/"},
        HTTP_HOST="testserver",
    )

    CHECK.assertEqual(get_safe_next_url(request), "")
