from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0009_runtime_deployment"),
    ]

    operations = [
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
