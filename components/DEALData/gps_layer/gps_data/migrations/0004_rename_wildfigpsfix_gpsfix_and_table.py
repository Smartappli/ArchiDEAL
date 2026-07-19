from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gps_data", "0003_alter_gpsrawdata_gps_raw_data_id_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="WildFiGPSFix",
            new_name="GPSFix",
        ),
        migrations.AlterModelTable(
            name="gpsfix",
            table="gps_fix",
        ),
    ]
