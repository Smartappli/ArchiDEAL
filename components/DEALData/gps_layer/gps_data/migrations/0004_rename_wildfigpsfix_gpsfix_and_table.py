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
        migrations.RenameIndex(
            model_name="gpsfix",
            old_name="gps_data_wi_wildfi__3f5d69_idx",
            new_name="gps_fix_wildfi__83ec1f_idx",
        ),
        migrations.RenameIndex(
            model_name="gpsfix",
            old_name="gps_data_wi_dealiot_bdc6e3_idx",
            new_name="gps_fix_dealiot_a9c637_idx",
        ),
    ]
