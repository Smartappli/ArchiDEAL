from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = REPO_ROOT / "airflow" / "dags" / "media_backfill.py"


def _load_dag_module(recorder: dict[str, Any]):
    fake_pendulum = types.ModuleType("pendulum")
    cast("Any", fake_pendulum).datetime = Mock(return_value="2026-01-01T00:00:00+01:00")

    fake_airflow = types.ModuleType("airflow")
    fake_providers = types.ModuleType("airflow.providers")
    fake_standard = types.ModuleType("airflow.providers.standard")
    fake_operators = types.ModuleType("airflow.providers.standard.operators")
    fake_bash = types.ModuleType("airflow.providers.standard.operators.bash")
    fake_sdk = types.ModuleType("airflow.sdk")

    def dag(**dag_kwargs):
        recorder["dag_kwargs"] = dag_kwargs

        def decorator(func):
            recorder["dag_function"] = func
            return func

        return decorator

    class _FakePartial:
        def __init__(self, **kwargs):
            recorder["partial_kwargs"] = kwargs

        def expand_kwargs(self, jobs):
            recorder["jobs"] = jobs
            return jobs

    class _FakeBashOperator:
        @staticmethod
        def partial(**kwargs):
            return _FakePartial(**kwargs)

    cast("Any", fake_sdk).dag = dag
    cast("Any", fake_bash).BashOperator = _FakeBashOperator

    with patch.dict(
        sys.modules,
        {
            "pendulum": fake_pendulum,
            "airflow": fake_airflow,
            "airflow.providers": fake_providers,
            "airflow.providers.standard": fake_standard,
            "airflow.providers.standard.operators": fake_operators,
            "airflow.providers.standard.operators.bash": fake_bash,
            "airflow.sdk": fake_sdk,
        },
    ):
        spec = importlib.util.spec_from_file_location("airflow_media_backfill_under_test", DAG_PATH)
        if spec is None:
            raise RuntimeError("Unable to load module spec for media_backfill DAG")
        if spec.loader is None:
            raise RuntimeError("Unable to load media_backfill DAG module loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class AirflowDagUnitTests(unittest.TestCase):
    def test_media_backfill_dag_expands_all_media_backfill_jobs(self) -> None:
        recorder: dict[str, Any] = {}

        module = _load_dag_module(recorder)

        self.assertTrue(callable(module.media_backfill))
        self.assertEqual(recorder["dag_kwargs"]["dag_id"], "media_backfill")
        self.assertEqual(recorder["dag_kwargs"]["schedule"], "*/30 * * * *")
        self.assertFalse(recorder["dag_kwargs"]["catchup"])
        self.assertEqual(
            recorder["partial_kwargs"], {"task_id": "backfill_media", "do_xcom_push": False}
        )

        jobs = recorder["jobs"]
        self.assertEqual(len(jobs), 4)
        commands = [job["bash_command"] for job in jobs]

        for bucket, media_kind in (
            ("media-raw-2d-images", "image2d"),
            ("media-raw-3d-images", "image3d"),
            ("media-raw-2d-videos", "video2d"),
            ("media-raw-3d-videos", "video3d"),
        ):
            matching = [command for command in commands if f"--bucket {bucket}" in command]
            self.assertEqual(len(matching), 1)
            self.assertIn(f"--media-kind {media_kind}", matching[0])
            self.assertIn("--window-start", matching[0])
            self.assertIn("--window-end", matching[0])
            self.assertIn("python3 /opt/pipelines/media_backfill.py", matching[0])


if __name__ == "__main__":
    unittest.main()
