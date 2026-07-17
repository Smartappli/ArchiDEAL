"""Django settings for the sensor service."""
# pylint: disable=unsubscriptable-object,wrong-import-position

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR.parent))

from dealdata_common.django_settings import configure_service_settings

configure_service_settings(
    globals(),
    base_dir=BASE_DIR,
    project_module="sensor",
    app_config="sensor_data.apps.SensorDataConfig",
    database_name="dealdata_sensor",
    include_wsgi=False,
    require_ingest_token=True,
)
