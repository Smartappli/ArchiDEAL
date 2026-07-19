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
        migrations.RenameIndex(
            model_name="decodedsensorevent",
            old_name="sensor_data_wildfi__ed21f6_idx",
            new_name="sensor_even_wildfi__4a7e5c_idx",
        ),
        migrations.RenameIndex(
            model_name="decodedsensorevent",
            old_name="sensor_data_dealiot_6036c3_idx",
            new_name="sensor_even_dealiot_64ecf0_idx",
        ),
        migrations.RenameIndex(
            model_name="decodedsensorevent",
            old_name="sensor_data_sensor__d7efa6_idx",
            new_name="sensor_even_sensor__a7f4ad_idx",
        ),
    ]
