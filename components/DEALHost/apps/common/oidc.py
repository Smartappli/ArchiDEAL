from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import unquote, urlsplit, urlunsplit


def derive_oidc_acl_username(issuer: str, subject: str) -> str:
    """Derive the opaque Django username used by direct OIDC dataset ACLs."""

    value = f"{issuer}\0{subject}".encode()
    return "oidc:" + hashlib.sha256(value).hexdigest()


def validate_canonical_oidc_issuer(value: str) -> str:
    """Require one unambiguous HTTPS representation of an OIDC issuer URL."""

    if not value or value != value.strip():
        raise ValueError("The OIDC issuer must not be empty or padded with whitespace.")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The OIDC issuer is not a valid URL.") from exc

    if parsed.scheme != "https":
        raise ValueError("The OIDC issuer must use canonical lowercase HTTPS.")
    if not parsed.hostname:
        raise ValueError("The OIDC issuer must include a host.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("The OIDC issuer must not contain user information.")
    if "%" in parsed.netloc:
        raise ValueError("The OIDC issuer host must not use percent encoding.")
    if parsed.query or parsed.fragment:
        raise ValueError("The OIDC issuer must not contain a query or fragment.")
    if port == 443:
        raise ValueError("The OIDC issuer must omit the default HTTPS port.")
    if "\\" in parsed.path or "//" in parsed.path:
        raise ValueError("The OIDC issuer path is not canonical.")
    if any(
        unquote(segment).casefold() in {".", ".."} for segment in parsed.path.split("/")
    ):
        raise ValueError("The OIDC issuer path must not contain dot segments.")

    hostname = parsed.hostname
    try:
        canonical_host = str(ipaddress.ip_address(hostname))
    except ValueError:
        try:
            canonical_host = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("The OIDC issuer host is not valid.") from exc
        if canonical_host.endswith("."):
            raise ValueError("The OIDC issuer host must not end with a dot.")
        labels = canonical_host.split(".")
        if len(canonical_host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("The OIDC issuer host is not a valid DNS name.")

    if ":" in canonical_host:
        canonical_host = f"[{canonical_host}]"
    canonical_netloc = canonical_host if port is None else f"{canonical_host}:{port}"
    canonical = urlunsplit(("https", canonical_netloc, parsed.path, "", ""))
    if canonical != value:
        raise ValueError(
            "The OIDC issuer must use its canonical form (lowercase host, "
            "IDNA host and no default port)."
        )
    return value


def validate_approved_oidc_issuer(value: str, approved_value: str) -> str:
    """Require the requested issuer to match the configured runtime issuer."""

    requested = validate_canonical_oidc_issuer(value)
    if not approved_value:
        raise ValueError(
            "OIDC identity provisioning is unavailable because no approved "
            "runtime issuer is configured."
        )
    try:
        approved = validate_canonical_oidc_issuer(approved_value)
    except ValueError as exc:
        raise ValueError(
            "OIDC identity provisioning is unavailable because the approved "
            "runtime issuer configuration is invalid."
        ) from exc
    if requested != approved:
        raise ValueError("The OIDC issuer is not approved for this deployment.")
    return requested


def validate_oidc_subject(value: str) -> str:
    """Validate an opaque, stable and non-empty OIDC subject identifier."""

    if not value or value != value.strip():
        raise ValueError(
            "The OIDC subject must not be empty or padded with whitespace."
        )
    if "\0" in value:
        raise ValueError("The OIDC subject contains an invalid null character.")
    return value
