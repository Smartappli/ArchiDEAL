"""API tests for staff-managed experiments."""

from uuid import UUID

from django.contrib.auth import get_user_model
import pytest
from rest_framework.test import APIClient

from .models import Experiment, ObservedObject, Project

EXPERIMENTS_URL = "/api/experiments/"
PROJECT_ONE_ID = UUID("00000000-0000-4000-8000-000000000001")
PROJECT_TWO_ID = UUID("00000000-0000-4000-8000-000000000002")
OBJECT_ONE_ID = UUID("00000000-0000-4000-8000-000000000011")
OBJECT_TWO_ID = UUID("00000000-0000-4000-8000-000000000012")
CLIENT_EXPERIMENT_ID = UUID("00000000-0000-4000-8000-000000000021")
MISSING_LINK_ID = UUID("00000000-0000-4000-8000-000000000099")


def create_user(username: str, *, is_staff: bool = False):
    """Create a local API user."""
    return get_user_model().objects.create_user(
        username=username,
        is_staff=is_staff,
    )


def create_project(owner, project_id: UUID, code: str) -> Project:
    """Create a project with a deterministic identifier."""
    return Project.objects.create(
        project_id=project_id,
        project_code=code,
        project_primary_owner=owner,
    )


def create_observed_object(object_id: UUID, code: str) -> ObservedObject:
    """Create an observed object with a deterministic identifier."""
    return ObservedObject.objects.create(
        observed_object_id=object_id,
        observed_object_code=code,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("authenticated", [False, True])
def test_experiment_api_rejects_users_without_staff_access(authenticated) -> None:
    """Anonymous and authenticated non-staff users cannot access experiments."""
    client = APIClient()
    if authenticated:
        client.force_authenticate(create_user("regular-user"))

    response = client.get(EXPERIMENTS_URL)

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_user_can_create_read_patch_and_delete_experiment() -> None:
    """A staff user can execute the complete supported experiment lifecycle."""
    staff_user = create_user("staff-user", is_staff=True)
    project_one = create_project(staff_user, PROJECT_ONE_ID, "PROJECT-ONE")
    project_two = create_project(staff_user, PROJECT_TWO_ID, "PROJECT-TWO")
    object_one = create_observed_object(OBJECT_ONE_ID, "OBJECT-ONE")
    object_two = create_observed_object(OBJECT_TWO_ID, "OBJECT-TWO")
    client = APIClient()
    client.force_authenticate(staff_user)

    create_response = client.post(
        EXPERIMENTS_URL,
        {
            "id": str(CLIENT_EXPERIMENT_ID),
            "project": str(project_one.project_id),
            "observed_objects": [str(object_one.observed_object_id)],
        },
        format="json",
    )

    assert create_response.status_code == 201
    experiment_id = create_response.json()["id"]
    assert experiment_id != str(CLIENT_EXPERIMENT_ID)
    assert create_response.json() == {
        "id": experiment_id,
        "project": str(project_one.project_id),
        "observed_objects": [str(object_one.observed_object_id)],
    }

    list_response = client.get(EXPERIMENTS_URL)
    detail_url = f"{EXPERIMENTS_URL}{experiment_id}/"
    detail_response = client.get(detail_url)

    assert list_response.status_code == 200
    assert list_response.json() == [create_response.json()]
    assert detail_response.status_code == 200
    assert detail_response.json() == create_response.json()

    patch_response = client.patch(
        detail_url,
        {
            "project": str(project_two.project_id),
            "observed_objects": [str(object_two.observed_object_id)],
        },
        format="json",
    )

    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": experiment_id,
        "project": str(project_two.project_id),
        "observed_objects": [str(object_two.observed_object_id)],
    }
    experiment = Experiment.objects.get(experiment_id=experiment_id)
    assert experiment.experiment_project == project_two
    assert list(experiment.experiment_observed_objects.all()) == [object_two]

    delete_response = client.delete(detail_url)

    assert delete_response.status_code == 204
    assert not Experiment.objects.filter(experiment_id=experiment_id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project", str(MISSING_LINK_ID)),
        ("observed_objects", [str(MISSING_LINK_ID)]),
    ],
)
def test_experiment_api_rejects_missing_related_entities(field, value) -> None:
    """Project and observed-object links must reference existing entities."""
    staff_user = create_user("validation-staff", is_staff=True)
    project = create_project(staff_user, PROJECT_ONE_ID, "VALID-PROJECT")
    observed_object = create_observed_object(OBJECT_ONE_ID, "VALID-OBJECT")
    payload = {
        "project": str(project.project_id),
        "observed_objects": [str(observed_object.observed_object_id)],
    }
    payload[field] = value
    client = APIClient()
    client.force_authenticate(staff_user)

    response = client.post(EXPERIMENTS_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.json()
    assert Experiment.objects.count() == 0


@pytest.mark.django_db
def test_experiment_detail_rejects_put() -> None:
    """The detail contract exposes PATCH, not full replacement with PUT."""
    staff_user = create_user("put-staff", is_staff=True)
    project = create_project(staff_user, PROJECT_ONE_ID, "PUT-PROJECT")
    experiment = Experiment.objects.create(experiment_project=project)
    client = APIClient()
    client.force_authenticate(staff_user)

    response = client.put(
        f"{EXPERIMENTS_URL}{experiment.experiment_id}/",
        {
            "project": str(project.project_id),
            "observed_objects": [],
        },
        format="json",
    )

    assert response.status_code == 405
