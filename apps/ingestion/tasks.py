from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def download_cur_task(self, job_id: int) -> int:
    from pathlib import Path
    from django.conf import settings
    from .models import CurDownloadJob, CurFile
    from .services.s3_downloader import download_cur_file, sha256_of_file

    job = CurDownloadJob.objects.get(id=job_id)
    job.status = "running"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    try:
        storage = settings.CUR_LOCAL_STORAGE / job.billing_period
        storage.mkdir(parents=True, exist_ok=True)
        total = 0
        for s3_key in job.s3_keys:
            filename = Path(s3_key).name
            local_path = storage / filename
            sha = download_cur_file(job.manifest, s3_key, local_path)
            size = local_path.stat().st_size
            CurFile.objects.create(
                job=job,
                s3_key=s3_key,
                local_path=str(local_path),
                file_hash_sha256=sha,
                size_bytes=size,
            )
            total += 1
        job.status = "success"
        job.completed_at = timezone.now()
        job.rows_downloaded = total
        job.save(update_fields=["status", "completed_at", "rows_downloaded"])
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.save(update_fields=["status", "error_message"])
        raise self.retry(exc=exc, countdown=60)

    return job_id


@shared_task(bind=True, max_retries=2)
def run_etl_task(self, job_id: int) -> str:
    from pathlib import Path
    from .models import CurDownloadJob
    from apps.etl.pipeline.reader import read_cur_file
    from apps.etl.pipeline.normalizer import normalize_schema
    from apps.etl.pipeline.deduplicator import deduplicate
    from apps.etl.pipeline.validator import validate
    from apps.etl.pipeline.loader import bulk_load
    from apps.etl.pipeline.aggregator import refresh_daily_aggregates, refresh_hourly_aggregates

    job = CurDownloadJob.objects.get(id=job_id)
    for cur_file in job.files.filter(etl_status="pending"):
        try:
            for chunk in read_cur_file(Path(cur_file.local_path)):
                df = normalize_schema(chunk)
                df = deduplicate(df, existing_ids=set())
                valid, _ = validate(df)
                bulk_load(valid)
            cur_file.etl_status = "processed"
            cur_file.save(update_fields=["etl_status"])
        except Exception as exc:
            cur_file.etl_status = "error"
            cur_file.save(update_fields=["etl_status"])
            raise self.retry(exc=exc, countdown=120)

    refresh_daily_aggregates(job.billing_period)
    refresh_hourly_aggregates(job.billing_period)
    return job.billing_period
