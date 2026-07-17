"""Views for authentication login workflows."""

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login
from django.shortcuts import redirect

from auth.views import AuthView

MISSING_CREDENTIALS_MESSAGE = "Please enter your username and password."
INVALID_EMAIL_MESSAGE = "Please enter a valid email."
INVALID_USERNAME_MESSAGE = "Please enter a valid username."


class LoginView(AuthView):
    """Handle user login requests."""

    def get(self, request, *args, **kwargs):
        """
        Display the login page for unauthenticated users.

        Args:
            request: Django HTTP request.
            *args: Positional URL arguments.
            **kwargs: Keyword URL arguments.

        Returns:
            An HTTP redirect response or the rendered login page.

        """
        if request.user.is_authenticated:
            return redirect("index")

        return super().get(request, *args, **kwargs)

    def post(self, request):
        """
        Authenticate the user and start a session.

        Args:
            request: Django HTTP request.

        Returns:
            An HTTP redirect response.

        """
        username = request.POST.get("email-username")
        password = request.POST.get("password")

        if not (username and password):
            messages.error(request, MISSING_CREDENTIALS_MESSAGE)
            return redirect("login")

        user_model = get_user_model()
        if "@" in username:
            user_email = user_model.objects.filter(email=username).first()
            if user_email is None:
                messages.error(request, INVALID_EMAIL_MESSAGE)
                return redirect("login")
            username = user_email.username

        user_email = user_model.objects.filter(username=username).first()
        if user_email is None:
            messages.error(request, INVALID_USERNAME_MESSAGE)
            return redirect("login")

        authenticated_user = authenticate(
            request,
            username=username,
            password=password,
        )
        if authenticated_user is not None:
            login(request, authenticated_user)
            return redirect("index")

        messages.error(request, INVALID_USERNAME_MESSAGE)
        return redirect("login")
