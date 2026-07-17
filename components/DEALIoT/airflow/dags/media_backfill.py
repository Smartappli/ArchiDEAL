import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag


@dag(
    dag_id="media_backfill",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Brussels"),
    schedule="*/30 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["media", "beam", "backfill"],
)
def media_backfill():
    jobs = [
        {
            "bash_command": (
                "python3 /opt/pipelines/media_backfill.py "
                "--bucket media-raw-2d-images "
                "--media-kind image2d "
                "--window-start '{{ data_interval_start.to_iso8601_string() }}' "
                "--window-end '{{ data_interval_end.to_iso8601_string() }}'"
            ),
        },
        {
            "bash_command": (
                "python3 /opt/pipelines/media_backfill.py "
                "--bucket media-raw-3d-images "
                "--media-kind image3d "
                "--window-start '{{ data_interval_start.to_iso8601_string() }}' "
                "--window-end '{{ data_interval_end.to_iso8601_string() }}'"
            ),
        },
        {
            "bash_command": (
                "python3 /opt/pipelines/media_backfill.py "
                "--bucket media-raw-2d-videos "
                "--media-kind video2d "
                "--window-start '{{ data_interval_start.to_iso8601_string() }}' "
                "--window-end '{{ data_interval_end.to_iso8601_string() }}'"
            ),
        },
        {
            "bash_command": (
                "python3 /opt/pipelines/media_backfill.py "
                "--bucket media-raw-3d-videos "
                "--media-kind video3d "
                "--window-start '{{ data_interval_start.to_iso8601_string() }}' "
                "--window-end '{{ data_interval_end.to_iso8601_string() }}'"
            ),
        },
    ]

    BashOperator.partial(
        task_id="backfill_media",
        do_xcom_push=False,
    ).expand_kwargs(jobs)


media_backfill()
