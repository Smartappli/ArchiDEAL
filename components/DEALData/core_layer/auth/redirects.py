"""Redirect helpers for authentication flows."""

from django.utils.http import url_has_allowed_host_and_scheme


def get_safe_next_url(request) -> str:
    """Return a same-host post-login redirect target or an empty string."""
    next_url = request.POST.get("next", "")
    allowed_hosts = {request.get_host()}
    require_https = request.is_secure()
    safe_url = url_has_allowed_host_and_scheme(next_url, allowed_hosts, require_https)
    if next_url and safe_url:
        return next_url
    return ""
