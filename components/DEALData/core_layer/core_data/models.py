"""Data models for the research core layer."""

# pylint: disable=arguments-differ,import-error,missing-kwoa,no-member
# pylint: disable=no-name-in-module
# pylint: disable=signature-differs,too-few-public-methods
# pylint: disable=unexpected-keyword-arg

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.constraints import UniqueConstraint
from django.db.models.enums import TextChoices
from django.db.models.fields.json import JSONField
from django.db.models.indexes import Index
from dealdata_common.models import uuid7_value


class ProjectRole(TextChoices):
    """Available roles for project members."""

    OWNER = "owner", "Owner"
    ADVISOR = "advisor", "Advisor"
    SCIENTIST = "scientist", "Scientist"
    TECHNICIAN = "technician", "Technician"
    VIEWER = "viewer", "Viewer"
    NONE = "none", "None"


class Project(models.Model):
    """A research project with owners and members."""

    project_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    project_code = models.CharField(
        max_length=64,
        unique=True,
    )
    project_primary_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="primary_owned_projects",
    )

    project_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMembership",
        related_name="projects",
        blank=True,
    )

    def __str__(self) -> str:
        """Return the project code."""
        return self.project_code

    def project_owners_qs(self):
        """Return all active owners linked to the project."""
        return self.project_members.filter(
            project_memberships__project_membership_project=self,
            project_memberships__project_membership_role=ProjectRole.OWNER,
            project_memberships__project_membership_is_active=True,
        ).distinct()


class ProjectMembership(models.Model):
    """Membership linking a user to a project with a specific role."""

    project_membership_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    project_membership_project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    project_membership_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    project_membership_role = models.CharField(
        max_length=16,
        choices=ProjectRole.choices,
        default=ProjectRole.NONE,
    )
    project_membership_is_active = models.BooleanField(default=True)

    project_membership_created_at = models.DateTimeField(auto_now_add=True)
    project_membership_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata for project memberships."""

        constraints = [
            UniqueConstraint(
                fields=[
                    "project_membership_project",
                    "project_membership_user",
                ],
                name="uq_project_membership_project_user",
            ),
        ]
        indexes = [
            Index(
                fields=[
                    "project_membership_project",
                    "project_membership_user",
                ],
            ),
            Index(
                fields=[
                    "project_membership_project",
                    "project_membership_role",
                ],
            ),
        ]

    def __str__(self) -> str:
        """Return a readable representation of the membership."""
        username = getattr(
            self.project_membership_user,
            "username",
            str(self.project_membership_user),
        )
        return (
            f"{self.project_membership_project.project_code} - "
            f"{username} - "
            f"{self.project_membership_role}"
        )

    def clean(self) -> None:
        """Ensure that a project always keeps at least one active owner."""
        if not self.project_membership_project_id:
            return

        old = None
        if self.pk:
            old = (
                ProjectMembership.objects.filter(pk=self.pk)
                .only(
                    "project_membership_role",
                    "project_membership_is_active",
                )
                .first()
            )

        was_owner = bool(
            old
            and old.project_membership_role == ProjectRole.OWNER
            and old.project_membership_is_active,
        )
        will_be_owner = (
            self.project_membership_role == ProjectRole.OWNER
            and self.project_membership_is_active
        )

        if was_owner and not will_be_owner:
            remaining = (
                ProjectMembership.objects.filter(
                    project_membership_project=self.project_membership_project,
                    project_membership_role=ProjectRole.OWNER,
                    project_membership_is_active=True,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if not remaining:
                message = "A project must have at least one active owner."
                raise ValidationError(message)

    def save(
        self,
        *args,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        """Validate the model before saving it."""
        self.full_clean()
        return super().save(
            *args,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )


class ObservedObject(models.Model):
    """An observed entity used in experiments."""

    observed_object_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    observed_object_code = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Observed Object Code",
        help_text="e.g.: cow 125, building n°2, vehicle 1-xxx xxx, etc.",
    )
    observed_object_extra_data = JSONField(
        default=dict,
        blank=True,
        verbose_name="Observed Object Associated Extra Data",
        help_text='e.g.: {name: "super cow", sex: "F"}',
    )
    observed_object_created_at = models.DateTimeField(auto_now_add=True)
    observed_object_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        """Return the observed object code."""
        return self.observed_object_code


class Experiment(models.Model):
    """An experiment attached to a project and observed objects."""

    experiment_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    experiment_project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="experiment_projects",
    )
    experiment_observed_objects = models.ManyToManyField(
        ObservedObject,
        through="ExperimentObservedObject",
        related_name="experiment_observed_objects",
    )

    def __str__(self) -> str:
        """Return a readable experiment identifier."""
        return str(self.experiment_id)


class ExperimentObservedObject(models.Model):
    """Link an experiment to an observed object."""

    experiment_observed_object_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    experiment_observed_object_experiment = models.ForeignKey(
        Experiment,
        on_delete=models.CASCADE,
        related_name="observed_object_links",
    )
    experiment_observed_object_observed_object = models.ForeignKey(
        ObservedObject,
        on_delete=models.CASCADE,
        related_name="experiment_links",
    )
    experiment_observed_object_created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        """Model metadata for experiment observed-object links."""

        constraints = [
            UniqueConstraint(
                fields=[
                    "experiment_observed_object_experiment",
                    "experiment_observed_object_observed_object",
                ],
                name="uq_experiment_observed_object",
            ),
        ]

    def __str__(self) -> str:
        """Return a readable link representation."""
        return (
            f"{self.experiment_observed_object_experiment_id} - "
            f"{self.experiment_observed_object_observed_object_id}"
        )
