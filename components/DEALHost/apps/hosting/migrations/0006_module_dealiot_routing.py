from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0005_alter_applicationversion_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="module",
            name="contract_topics",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="module",
            name="deployment_target",
            field=models.CharField(
                choices=[
                    ("compose", "Docker Compose"),
                    ("swarm", "Docker Swarm"),
                    ("kubernetes", "Kubernetes"),
                    ("external", "External service"),
                ],
                default="compose",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="module",
            name="healthcheck_path",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="module",
            name="public_path",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="module",
            name="repository_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="module",
            name="repository_owner",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="module",
            name="source_path",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="module",
            name="upstream_host",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="module",
            name="upstream_port",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
