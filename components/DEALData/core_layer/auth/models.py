"""Models for the authentication application."""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    """Profile associated with a Django user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    email = models.EmailField(
        max_length=100,
        unique=True,
    )
    email_token = models.CharField(max_length=100, blank=True, null=True)
    forget_password_token = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    forget_password_token_expires_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Metadata for the Profile model."""

        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        """Return the username linked to this profile."""
        return self.user.username


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    """Create a profile automatically when a new user is created."""
    del sender, kwargs
    if created:
        Profile.objects.create(user=instance, email=instance.email)
