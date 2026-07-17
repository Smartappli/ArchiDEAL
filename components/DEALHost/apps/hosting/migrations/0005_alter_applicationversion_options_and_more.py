from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0004_dataset"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="applicationversion",
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Application version",
                "verbose_name_plural": "Application versions",
            },
        ),
        migrations.AlterModelOptions(
            name="hostedapplication",
            options={
                "verbose_name": "Application",
                "verbose_name_plural": "Applications",
            },
        ),
        migrations.AlterModelOptions(
            name="module",
            options={
                "verbose_name": "Module",
                "verbose_name_plural": "Modules",
            },
        ),
        migrations.AlterModelOptions(
            name="tool",
            options={
                "verbose_name": "Tool",
                "verbose_name_plural": "Tools",
            },
        ),
        migrations.AlterModelOptions(
            name="toolversion",
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Tool version",
                "verbose_name_plural": "Tool versions",
            },
        ),
    ]
