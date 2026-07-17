"""Admin configuration for authentication models."""

from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class Member(admin.ModelAdmin):
    """Admin configuration for the profile model."""

    list_display = ("user", "email", "is_verified", "created_at")
