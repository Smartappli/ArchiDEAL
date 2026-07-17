"""Tests for the core_data application."""

from unittest import TestCase
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client
import pytest

from dealdata_common.django_settings import env_float, env_int
from core_data.models import (
    Experiment,
    ExperimentObservedObject,
    ObservedObject,
    Project,
    ProjectMembership,
    ProjectRole,
    uuid7_value,
)

CHECK = TestCase()


def test_env_int_returns_default_when_unset(monkeypatch) -> None:
    """Optional numeric settings use their documented default value."""
    monkeypatch.delenv("DEALDATA_TEST_INTEGER", raising=False)

    CHECK.assertEqual(
        env_int("DEALDATA_TEST_INTEGER", default=60, minimum=0),
        60,
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [("not-an-integer", "integer"), ("-1", "greater than or equal")],
)
def test_env_int_rejects_invalid_values(monkeypatch, value: str, message: str) -> None:
    """Integer settings fail with an actionable configuration error."""
    monkeypatch.setenv("DEALDATA_TEST_INTEGER", value)

    with pytest.raises(RuntimeError, match=message):
        env_int("DEALDATA_TEST_INTEGER", default=60, minimum=0)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("NaN", "finite"),
        ("-0.1", "greater than or equal"),
        ("1.1", "less than or equal"),
    ],
)
def test_env_float_rejects_invalid_sample_rates(
    monkeypatch,
    value: str,
    message: str,
) -> None:
    """Float settings reject non-finite and out-of-range values."""
    monkeypatch.setenv("DEALDATA_TEST_FLOAT", value)

    with pytest.raises(RuntimeError, match=message):
        env_float(
            "DEALDATA_TEST_FLOAT",
            default=0.0,
            minimum=0.0,
            maximum=1.0,
        )


def create_test_user(username: str):
    """Create a user through the configured Django user model."""
    return get_user_model().objects.create_user(username=username)


def test_project_string_representation() -> None:
    """Project instances are represented by their code."""
    project = Project(project_code="DEAL-CORE")

    CHECK.assertEqual(str(project), "DEAL-CORE")


def test_observed_object_string_representation() -> None:
    """Observed objects are represented by their code."""
    observed_object = ObservedObject(observed_object_code="OBJ-001")

    CHECK.assertEqual(str(observed_object), "OBJ-001")


def test_uuid7_value_returns_standard_uuid() -> None:
    """UUID defaults are compatible with Django UUIDField validation."""
    value = uuid7_value()

    CHECK.assertEqual(value.version, 7)


@pytest.mark.django_db
def test_project_membership_string_representation() -> None:
    """Memberships expose project, user and role in their string form."""
    user = create_test_user(username="alice")
    project = Project.objects.create(
        project_code="DEAL-001",
        project_primary_owner=user,
    )
    membership = ProjectMembership.objects.create(
        project_membership_project=project,
        project_membership_user=user,
        project_membership_role=ProjectRole.OWNER,
    )

    CHECK.assertEqual(str(membership), "DEAL-001 - alice - owner")


@pytest.mark.django_db
def test_project_membership_rejects_removing_last_owner() -> None:
    """A project must keep at least one active owner."""
    user = create_test_user(username="owner")
    project = Project.objects.create(
        project_code="DEAL-002",
        project_primary_owner=user,
    )
    membership = ProjectMembership.objects.create(
        project_membership_project=project,
        project_membership_user=user,
        project_membership_role=ProjectRole.OWNER,
    )

    membership.project_membership_role = ProjectRole.VIEWER

    with pytest.raises(ValidationError):
        membership.full_clean()


@pytest.mark.django_db
def test_project_owners_qs_returns_active_owners() -> None:
    """Project owners query excludes inactive or non-owner memberships."""
    owner = create_test_user(username="owner")
    viewer = create_test_user(username="viewer")
    project = Project.objects.create(
        project_code="DEAL-003",
        project_primary_owner=owner,
    )
    ProjectMembership.objects.create(
        project_membership_project=project,
        project_membership_user=owner,
        project_membership_role=ProjectRole.OWNER,
    )
    ProjectMembership.objects.create(
        project_membership_project=project,
        project_membership_user=viewer,
        project_membership_role=ProjectRole.VIEWER,
    )

    CHECK.assertEqual(list(project.project_owners_qs()), [owner])


@pytest.mark.django_db
def test_experiment_links_string_representations() -> None:
    """Experiments and experiment-object links have stable string output."""
    user = create_test_user(username="scientist")
    project = Project.objects.create(
        project_code="DEAL-004",
        project_primary_owner=user,
    )
    observed_object = ObservedObject.objects.create(
        observed_object_code="OBJ-004",
    )
    experiment = Experiment.objects.create(experiment_project=project)
    link = ExperimentObservedObject.objects.create(
        experiment_observed_object_experiment=experiment,
        experiment_observed_object_observed_object=observed_object,
    )

    CHECK.assertEqual(str(experiment), str(experiment.experiment_id))
    CHECK.assertEqual(
        str(link), f"{experiment.experiment_id} - {observed_object.observed_object_id}"
    )


def test_health_live() -> None:
    """The liveness endpoint returns a cheap OK response."""
    response = Client().get("/health/live/")

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.json()["status"], "ok")


def test_health_ready(db) -> None:
    """The readiness endpoint checks database access."""
    del db
    response = Client().get("/health/ready/")

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.json()["database"], "available")


def test_health_ready_reports_generic_database_failure() -> None:
    """Readiness failures do not expose database exception details."""
    with patch("core_data.views.connections") as mocked_connections:
        mocked_connections.__getitem__.side_effect = DatabaseError(
            "database password leaked",
        )
        response = Client().get("/health/ready/")

    body = response.json()
    CHECK.assertEqual(response.status_code, 503)
    CHECK.assertEqual(body["database"], "unavailable")
    CHECK.assertEqual(body["detail"], "Database connection check failed.")
    CHECK.assertNotIn("password", str(body))


@pytest.mark.parametrize(
    "path",
    ["/health/live/", "/health/ready/", "/metrics/"],
)
def test_observability_endpoints_reject_unsafe_methods(path: str) -> None:
    """Read-only observability endpoints reject unsafe HTTP methods."""
    response = Client().post(path)

    CHECK.assertEqual(response.status_code, 405)
    CHECK.assertEqual(response.headers["Allow"], "GET, HEAD")


@pytest.mark.django_db
def test_metrics_exposes_prometheus_counts() -> None:
    """Metrics endpoint exposes core domain counters."""
    user = create_test_user(username="metrics-owner")
    Project.objects.create(
        project_code="DEAL-METRICS",
        project_primary_owner=user,
    )
    ObservedObject.objects.create(observed_object_code="OBJ-METRICS")

    response = Client().get("/metrics/")
    text = response.content.decode()

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertIn("dealdata_core_projects_total 1", text)
    CHECK.assertIn("dealdata_core_observed_objects_total 1", text)
