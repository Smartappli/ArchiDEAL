"""Views for user registration workflows."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.shortcuts import redirect

from auth.helpers import send_verification_email
from auth.models import Profile
from auth.tokens import generate_url_token, hash_url_token
from auth.views import AuthView

EMAIL_NOT_CONFIGURED_MESSAGE = (
    "Email settings are not configured. Unable to send verification email."
)
VERIFICATION_EMAIL_SENT_MESSAGE = "Verification email sent successfully"
MISSING_FIELDS_MESSAGE = "Please fill in all required fields."
USER_ALREADY_EXISTS_MESSAGE = "User already exists. Try logging in."
EMAIL_ALREADY_EXISTS_MESSAGE = "Email already exists."
USERNAME_ALREADY_EXISTS_MESSAGE = "Username already exists."
DEFAULT_GROUP_NAME = "client"


def get_registration_group() -> Group:
    """Return the default group assigned to newly registered users."""
    group = Group.objects.filter(name=DEFAULT_GROUP_NAME).first()
    if group:
        return group
    try:
        return Group.objects.create(name=DEFAULT_GROUP_NAME)
    except IntegrityError:
        return Group.objects.get(name=DEFAULT_GROUP_NAME)


def get_user_profile(user) -> Profile:
    """Return a user's profile, creating it if the signal did not."""
    profile = Profile.objects.filter(user=user).first()
    if profile:
        return profile
    try:
        return Profile.objects.create(user=user, email=user.email)
    except IntegrityError:
        return Profile.objects.get(user=user)


class RegisterView(AuthView):
    """Handle user registration and email verification setup."""

    def get(self, request, *args, **kwargs):
        """
        Display the registration page.

        Args:
            request: Django HTTP request.
            *args: Positional URL arguments.
            **kwargs: Keyword URL arguments.

        Returns:
            An HTTP redirect response or the rendered registration page.

        """
        if request.user.is_authenticated:
            return redirect("index")

        return super().get(request, *args, **kwargs)

    def post(self, request):
        """
        Create a new user account and send a verification email.

        Args:
            request: Django HTTP request.

        Returns:
            An HTTP redirect response.

        """
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        if not (username and email and password):
            messages.error(request, MISSING_FIELDS_MESSAGE)
            return redirect("register")

        user_model = get_user_model()
        if user_model.objects.filter(username=username, email=email).exists():
            messages.error(request, USER_ALREADY_EXISTS_MESSAGE)
            return redirect("register")

        if user_model.objects.filter(email=email).exists():
            messages.error(request, EMAIL_ALREADY_EXISTS_MESSAGE)
            return redirect("register")

        if user_model.objects.filter(username=username).exists():
            messages.error(request, USERNAME_ALREADY_EXISTS_MESSAGE)
            return redirect("register")

        created_user = user_model.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        user_group = get_registration_group()
        created_user.groups.add(user_group)

        verification_token = generate_url_token()

        user_profile = get_user_profile(created_user)
        user_profile.email_token = hash_url_token(verification_token)
        user_profile.email = email
        user_profile.save()

        send_verification_email(email, verification_token)

        if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
            messages.success(request, VERIFICATION_EMAIL_SENT_MESSAGE)
        else:
            messages.error(request, EMAIL_NOT_CONFIGURED_MESSAGE)

        request.session["email"] = email
        return redirect("verify-email-page")
