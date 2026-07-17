"""Views for password reset workflows."""

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.utils import timezone

from auth.models import Profile
from auth.tokens import hash_url_token
from auth.views import AuthView


class ResetPasswordView(AuthView):
    """Handle password reset requests using a reset token."""

    def get(self, request, *args, **kwargs):
        """
        Display the password reset form.

        Args:
            request: Django HTTP request.
            *args: Positional URL arguments.
            **kwargs: Keyword URL arguments.

        Returns:
            An HTTP redirect response or the rendered reset password page.

        """
        if request.user.is_authenticated:
            return redirect("index")

        return super().get(request, *args, **kwargs)

    def post(self, request, token):
        """
        Reset the user's password if the provided token is valid.

        Args:
            request: Django HTTP request.
            token: Password reset token from the URL.

        Returns:
            An HTTP redirect response or the rendered reset password page.

        """
        token_hash = hash_url_token(token)
        profile_qs = Profile.objects.filter(forget_password_token=token_hash)
        profile = profile_qs.first()
        if not profile:
            messages.error(request, "Invalid or expired token.")
            return redirect("forgot-password")

        expires_at = profile.forget_password_token_expires_at
        reset_token_expired = expires_at and timezone.now() > expires_at
        if reset_token_expired:
            profile.forget_password_token = None
            profile.forget_password_token_expires_at = None
            profile.save()
            messages.error(request, "Invalid or expired token.")
            return redirect("forgot-password")

        new_password = request.POST.get("password")
        confirm_password = request.POST.get("confirm-password")

        if not (new_password and confirm_password):
            messages.error(request, "Please fill all fields.")
            return render(request, self.template_name)

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, self.template_name)

        user = profile.user
        user.set_password(new_password)
        user.save()

        profile.forget_password_token = None
        profile.forget_password_token_expires_at = None
        profile.save()

        authenticated_user = authenticate(
            request,
            username=user.username,
            password=new_password,
        )
        if authenticated_user:
            login(request, authenticated_user)
            return redirect("index")

        messages.success(request, "Password reset successful. Please log in.")
        return redirect("login")
