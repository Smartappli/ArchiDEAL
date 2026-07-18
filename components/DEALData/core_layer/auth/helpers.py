"""Helper functions for authentication emails and URL generation."""

import logging
from smtplib import SMTPException
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

LOGGER = logging.getLogger(__name__)


def send_email(subject, email, message):
    """
    Send an email using Django's configured email backend.

    Args:
        subject: Email subject line.
        email: Recipient email address.
        message: Plain-text email body.

    Notes:
        - Errors are logged with the module logger to aid diagnostics.

    """
    email_from = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(
        settings,
        "EMAIL_HOST_USER",
        None,
    )
    if not email_from:
        LOGGER.warning("Email sender is not configured; skipping send.")
        return
    if not email:
        LOGGER.warning("No recipient email provided; skipping send.")
        return

    recipient_list = [email]
    email_message = EmailMessage(subject, message, email_from, recipient_list)
    try:
        email_message.send()
    except (OSError, SMTPException):
        LOGGER.exception("Failed to send email.")


def get_absolute_url(path):
    """
    Build an absolute URL from a relative path.

    Args:
        path: A relative URL path, typically returned by
            `django.urls.reverse()`, such as "/verify/abc123/".

    Returns:
        An absolute URL combining `settings.BASE_URL` and the provided path.

    """
    return urljoin(settings.BASE_URL, path)


def send_verification_email(email, token):
    """
    Send an email verification link to a user.

    Args:
        email: Recipient email address.
        token: Verification token embedded into the URL.

    Side effects:
        Sends an email with a link pointing to the `verify-email` route.

    """
    subject = "Verify your email"
    verification_url = get_absolute_url(
        reverse("verify-email", kwargs={"token": token}),
    )
    message = f"Hi,\n\nPlease verify your email using this link: {verification_url}"
    send_email(subject, email, message)


def send_password_reset_email(email, token):
    """
    Send a password reset link to a user.

    Args:
        email: Recipient email address.
        token: Password reset token embedded into the URL.

    Side effects:
        Sends an email with a link pointing to the `reset-password` route.

    """
    subject = "Reset your password"
    reset_url = get_absolute_url(
        reverse("reset-password", kwargs={"token": token}),
    )
    message = f"Hi,\n\nPlease reset your password using this link: {reset_url}"
    send_email(subject, email, message)
