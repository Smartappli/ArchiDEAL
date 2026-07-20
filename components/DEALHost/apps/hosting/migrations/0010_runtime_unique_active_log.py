from django.db import migrations, models
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone


def fail_duplicate_active_logs(apps, schema_editor):
    runtime_operation = apps.get_model("hosting", "RuntimeOperation")
    duplicate_deployments = (
        runtime_operation.objects.filter(
            operation_type="log_snapshot",
            status__in=["queued", "running"],
        )
        .values("deployment_id")
        .annotate(active_count=models.Count("id"))
        .filter(active_count__gt=1)
    )
    for group in duplicate_deployments.iterator():
        # Preserve the oldest RUNNING capture because it may already have reached
        # the controller; if none started, preserve the oldest QUEUED request.
        candidates = runtime_operation.objects.filter(
            deployment_id=group["deployment_id"],
            operation_type="log_snapshot",
            status__in=["queued", "running"],
        ).order_by(
            Case(
                When(status="running", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "requested_at",
            "id",
        )
        keeper = candidates.first()
        if keeper is None:
            continue
        candidates.exclude(pk=keeper.pk).update(
            status="failed",
            error={
                "code": "duplicate_active_log_migrated",
                "detail": (
                    "This duplicate log snapshot was closed while enforcing the "
                    "single-active-snapshot invariant."
                ),
                "retryable": True,
            },
            progress={"stage": "failed", "percent": 100},
            finished_at=timezone.now(),
            next_attempt_at=None,
            leased_by="",
            lease_token=None,
            lease_expires_at=None,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0009_runtime_deployment"),
    ]

    operations = [
        migrations.RunPython(fail_duplicate_active_logs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="runtimeoperation",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    operation_type="log_snapshot",
                    status__in=["queued", "running"],
                ),
                fields=("deployment",),
                name="hosting_runtime_unique_active_log",
            ),
        ),
    ]
