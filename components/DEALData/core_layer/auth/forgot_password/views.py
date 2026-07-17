"""Views for forgot-password workflows."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.shortcuts import redirect
from django.utils import timezone

from auth.helpers import send_password_reset_email
from auth.models import Profile
from auth.tokens import generate_url_token, hash_url_token
from auth.views import AuthView

MISSING_EMAIL_MESSAGE = "Please enter your email address."
RESET_LINK_SENT_MESSAGE = (
    "If an account exists for that email, a reset link has been sent."
)
EMAIL_NOT_CONFIGURED_MESSAGE = (
    "Email settings are not configured. Unable to send verification email."
)
RESET_TOKEN_EXPIRATION_HOURS = 24


def get_password_reset_profile(user) -> Profile:
    """Return a user's profile, creating it if the signal did not."""
    profile = Profile.objects.filter(user=user).first()
    if profile:
        return profile
    try:
        return Profile.objects.create(user=user, email=user.email)
    except IntegrityError:
        return Profile.objects.get(user=user)


class ForgetPasswordView(AuthView):
    """Handle password reset requests initiated by email."""

    def get(self, request, *args, **kwargs):
        """
        Display the forgot-password page.

        Args:
            request: Django HTTP request.
            *args: Positional URL arguments.
            **kwargs: Keyword URL arguments.

        Returns:
            An HTTP redirect response or the rendered forgot-password page.

        """
        if request.user.is_authenticated:
            return redirect("index")

        return super().get(request, *args, **kwargs)

    def post(self, request):
        """
        Generate and send a password reset link when possible.

        Args:
            request: Django HTTP request.

        Returns:
            An HTTP redirect response.

        """
        email = request.POST.get("email")
        if not email:
            messages.error(request, MISSING_EMAIL_MESSAGE)
            return redirect("forgot-password")

        user_model = get_user_model()
        user = user_model.objects.filter(email=email).first()
        reset_token = generate_url_token()
        expiration_time = timezone.now() + timedelta(
            hours=RESET_TOKEN_EXPIRATION_HOURS,
        )

        if user:
            user_profile = get_password_reset_profile(user)
            user_profile.forget_password_token = hash_url_token(reset_token)
            user_profile.forget_password_token_expires_at = expiration_time
            user_profile.save()

            send_password_reset_email(email, reset_token)

        if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
            messages.success(request, RESET_LINK_SENT_MESSAGE)
        else:
            messages.error(request, EMAIL_NOT_CONFIGURED_MESSAGE)

        return redirect("forgot-password")
