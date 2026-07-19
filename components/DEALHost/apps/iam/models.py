from django.conf import settings
from django.db import models


class OIDCAclIdentity(models.Model):
    """Stable OIDC identity bound to an unprivileged technical ACL user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="oidc_acl_identity",
    )
    issuer = models.URLField(max_length=512)
    subject = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("issuer", "subject")
        constraints = [
            models.UniqueConstraint(
                fields=("issuer", "subject"),
                name="iam_oidc_acl_identity_issuer_subject_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name or f"{self.issuer} :: {self.subject}"
