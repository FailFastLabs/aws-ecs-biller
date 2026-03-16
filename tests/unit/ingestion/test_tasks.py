"""Tests for ingestion Celery tasks using mocking."""
import pytest
from unittest.mock import patch, MagicMock


def _make_job(billing_period="2025-01"):
    from apps.accounts.models import AwsAccount, CurManifest
    from apps.ingestion.models import CurDownloadJob

    account, _ = AwsAccount.objects.get_or_create(
        account_id="123456789012",
        defaults={"account_name": "Test", "is_payer": True},
    )
    manifest, _ = CurManifest.objects.get_or_create(
        account=account,
        report_name="test-cur",
        defaults={
            "s3_bucket": "my-bucket",
            "s3_prefix": "cur/",
            "time_unit": "HOURLY",
            "compression": "GZIP",
            "aws_region": "us-east-1",
        },
    )
    return CurDownloadJob.objects.create(
        manifest=manifest,
        billing_period=billing_period,
        s3_keys=["cur/2025-01/report.csv.gz"],
        status="pending",
    )


@pytest.mark.django_db
def test_download_cur_task_success():
    from apps.ingestion.tasks import download_cur_task

    job = _make_job()
    mock_stat = MagicMock()
    mock_stat.st_size = 1024

    # Tasks import these inside the function body — patch at the source module
    with patch("apps.ingestion.services.s3_downloader.download_cur_file", return_value="abc123"):
        with patch("apps.ingestion.tasks.download_cur_file", return_value="abc123", create=True):
            pass  # unused — actual patch path below
    with patch("apps.ingestion.services.s3_downloader.sha256_of_file"):
        pass

    # Correct approach: patch where they're imported *from* inside the task
    with patch("apps.ingestion.services.s3_downloader.download_cur_file", return_value="abc123sha256") as mock_dl, \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.stat", return_value=mock_stat):
        # Re-import inside function context so the local `from .services...` picks up mock
        import importlib
        import apps.ingestion.services.s3_downloader as s3mod
        original_fn = s3mod.download_cur_file
        s3mod.download_cur_file = MagicMock(return_value="abc123sha256")
        try:
            result = download_cur_task(job.id)
        finally:
            s3mod.download_cur_file = original_fn

    assert result == job.id
    job.refresh_from_db()
    assert job.status == "success"
    assert job.rows_downloaded == 1


@pytest.mark.django_db
def test_download_cur_task_failure():
    from apps.ingestion.tasks import download_cur_task
    from celery.exceptions import Retry
    import apps.ingestion.services.s3_downloader as s3mod

    job = _make_job(billing_period="2025-04")
    original_fn = s3mod.download_cur_file
    s3mod.download_cur_file = MagicMock(side_effect=Exception("S3 error"))
    try:
        with patch("pathlib.Path.mkdir"):
            with pytest.raises((Retry, Exception)):
                download_cur_task(job.id)
    finally:
        s3mod.download_cur_file = original_fn

    job.refresh_from_db()
    assert job.status == "failed"
    assert "S3 error" in job.error_message


@pytest.mark.django_db
def test_run_etl_task_processes_pending_files():
    from apps.ingestion.tasks import run_etl_task
    from apps.ingestion.models import CurFile
    import apps.etl.pipeline.reader as reader_mod
    import apps.etl.pipeline.normalizer as norm_mod
    import apps.etl.pipeline.deduplicator as dedup_mod
    import apps.etl.pipeline.validator as val_mod
    import apps.etl.pipeline.loader as loader_mod
    import apps.etl.pipeline.aggregator as agg_mod

    job = _make_job()
    CurFile.objects.create(
        job=job, s3_key="cur/2025-01/r.csv",
        local_path="/tmp/r.csv", file_hash_sha256="dead", size_bytes=10,
        etl_status="pending",
    )

    mock_df = MagicMock()
    _saved = {
        "read": reader_mod.read_cur_file,
        "norm": norm_mod.normalize_schema,
        "dedup": dedup_mod.deduplicate,
        "val": val_mod.validate,
        "load": loader_mod.bulk_load,
        "daily": agg_mod.refresh_daily_aggregates,
        "hourly": agg_mod.refresh_hourly_aggregates,
    }
    reader_mod.read_cur_file = MagicMock(return_value=[mock_df])
    norm_mod.normalize_schema = MagicMock(return_value=mock_df)
    dedup_mod.deduplicate = MagicMock(return_value=mock_df)
    val_mod.validate = MagicMock(return_value=(mock_df, mock_df))
    loader_mod.bulk_load = MagicMock()
    agg_mod.refresh_daily_aggregates = MagicMock()
    agg_mod.refresh_hourly_aggregates = MagicMock()
    try:
        result = run_etl_task(job.id)
    finally:
        reader_mod.read_cur_file = _saved["read"]
        norm_mod.normalize_schema = _saved["norm"]
        dedup_mod.deduplicate = _saved["dedup"]
        val_mod.validate = _saved["val"]
        loader_mod.bulk_load = _saved["load"]
        agg_mod.refresh_daily_aggregates = _saved["daily"]
        agg_mod.refresh_hourly_aggregates = _saved["hourly"]

    assert result == "2025-01"
    assert CurFile.objects.get(job=job).etl_status == "processed"


@pytest.mark.django_db
def test_run_etl_task_marks_file_error_on_exception():
    from apps.ingestion.tasks import run_etl_task
    from apps.ingestion.models import CurFile
    from celery.exceptions import Retry
    import apps.etl.pipeline.reader as reader_mod
    import apps.etl.pipeline.aggregator as agg_mod

    job = _make_job(billing_period="2025-05")
    CurFile.objects.create(
        job=job, s3_key="cur/2025-05/r.csv",
        local_path="/tmp/bad.csv", file_hash_sha256="bad", size_bytes=10,
        etl_status="pending",
    )

    original_read = reader_mod.read_cur_file
    original_daily = agg_mod.refresh_daily_aggregates
    original_hourly = agg_mod.refresh_hourly_aggregates
    reader_mod.read_cur_file = MagicMock(side_effect=IOError("File not found"))
    agg_mod.refresh_daily_aggregates = MagicMock()
    agg_mod.refresh_hourly_aggregates = MagicMock()
    try:
        with pytest.raises((Retry, Exception)):
            run_etl_task(job.id)
    finally:
        reader_mod.read_cur_file = original_read
        agg_mod.refresh_daily_aggregates = original_daily
        agg_mod.refresh_hourly_aggregates = original_hourly

    assert CurFile.objects.get(job=job).etl_status == "error"


@pytest.mark.django_db
def test_run_etl_task_skips_non_pending_files():
    from apps.ingestion.tasks import run_etl_task
    from apps.ingestion.models import CurFile
    import apps.etl.pipeline.reader as reader_mod
    import apps.etl.pipeline.aggregator as agg_mod

    job = _make_job(billing_period="2025-06")
    CurFile.objects.create(
        job=job, s3_key="cur/2025-06/r.csv",
        local_path="/tmp/done.csv", file_hash_sha256="cafe", size_bytes=20,
        etl_status="processed",
    )

    original_read = reader_mod.read_cur_file
    original_daily = agg_mod.refresh_daily_aggregates
    original_hourly = agg_mod.refresh_hourly_aggregates
    mock_read = MagicMock()
    reader_mod.read_cur_file = mock_read
    agg_mod.refresh_daily_aggregates = MagicMock()
    agg_mod.refresh_hourly_aggregates = MagicMock()
    try:
        result = run_etl_task(job.id)
    finally:
        reader_mod.read_cur_file = original_read
        agg_mod.refresh_daily_aggregates = original_daily
        agg_mod.refresh_hourly_aggregates = original_hourly

    mock_read.assert_not_called()
    assert result == "2025-06"
