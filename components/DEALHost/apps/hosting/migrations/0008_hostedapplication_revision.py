from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hosting", "0007_dataset_revision_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostedapplication",
            name="revision",
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
