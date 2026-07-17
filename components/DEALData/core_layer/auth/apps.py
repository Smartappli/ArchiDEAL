"""Application configuration for the authentication app."""

from django.apps import AppConfig


class AuthConfig(AppConfig):
    """Configure the authentication Django application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "auth"
    label = "accounts"
