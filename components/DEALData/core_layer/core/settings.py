"""Django settings for the core service."""
# pylint: disable=unsubscriptable-object,wrong-import-position

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR.parent))

from dealdata_common.django_settings import configure_service_settings

configure_service_settings(
    globals(),
    base_dir=BASE_DIR,
    project_module="core",
    app_config="core_data.apps.CoreDataConfig",
    database_name="dealdata_core",
)
