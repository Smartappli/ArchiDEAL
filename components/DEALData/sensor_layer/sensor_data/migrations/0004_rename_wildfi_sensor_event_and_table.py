from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("sensor_data", "0003_alter_sensor_sensor_id_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="WildFiDecodedSensorEvent",
            new_name="DecodedSensorEvent",
        ),
        migrations.AlterModelTable(
            name="decodedsensorevent",
            table="sensor_event",
        ),
    ]
