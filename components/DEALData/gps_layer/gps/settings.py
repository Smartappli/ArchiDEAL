"""Django settings for the GPS service."""
# pylint: disable=unsubscriptable-object,wrong-import-position

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR.parent))

from dealdata_common.django_settings import configure_service_settings

configure_service_settings(
    globals(),
    base_dir=BASE_DIR,
    project_module="gps",
    app_config="gps_data.apps.GpsConfig",
    database_name="dealdata_gps",
    require_ingest_token=True,
)
