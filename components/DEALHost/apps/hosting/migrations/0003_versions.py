from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0002_tool_hostedapplication"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostedapplication",
            name="current_version",
            field=models.CharField(default="0.1.0", max_length=32),
        ),
        migrations.AddField(
            model_name="hostedapplication",
            name="released_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hostedapplication",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="tool",
            name="current_version",
            field=models.CharField(default="0.1.0", max_length=32),
        ),
        migrations.AddField(
            model_name="tool",
            name="released_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tool",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.CreateModel(
            name="ToolVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.CharField(max_length=32)),
                ("notes", models.TextField(blank=True)),
                ("source", models.CharField(default="manual", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tool",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="versions",
                        to="hosting.tool",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "unique_together": {("tool", "version")},
            },
        ),
        migrations.CreateModel(
            name="ApplicationVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.CharField(max_length=32)),
                ("notes", models.TextField(blank=True)),
                ("source", models.CharField(default="manual", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="versions",
                        to="hosting.hostedapplication",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "unique_together": {("application", "version")},
            },
        ),
    ]
