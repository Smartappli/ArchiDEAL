from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tool",
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
                ("name", models.CharField(max_length=80, unique=True)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("description", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "modules",
                    models.ManyToManyField(
                        blank=True,
                        related_name="tools",
                        to="hosting.module",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="HostedApplication",
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
                ("name", models.CharField(max_length=80, unique=True)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("description", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "modules",
                    models.ManyToManyField(
                        blank=True,
                        related_name="applications",
                        to="hosting.module",
                    ),
                ),
            ],
        ),
    ]
