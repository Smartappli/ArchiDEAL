from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("hosting", "0006_module_dealiot_routing")]

    operations = [
        migrations.AddField(
            model_name="dataset",
            name="revision",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="dataset",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
