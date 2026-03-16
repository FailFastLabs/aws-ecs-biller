from django.db import models


class CurDownloadJob(models.Model):
    STATUS = [
        ("pending", "pending"),
        ("running", "running"),
        ("success", "success"),
        ("failed", "failed"),
    ]
    manifest = models.ForeignKey("accounts.CurManifest", on_delete=models.CASCADE, related_name="jobs")
    billing_period = models.CharField(max_length=20)
    s3_keys = models.JSONField(default=list)
    status = models.CharField(choices=STATUS, default="pending", max_length=10)
    celery_task_id = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    rows_downloaded = models.BigIntegerField(default=0)

    def __str__(self):
        return f"Job {self.id} ({self.billing_period}) [{self.status}]"


class CurFile(models.Model):
    ETL_STATUS = [("pending", "pending"), ("processed", "processed"), ("error", "error")]
    job = models.ForeignKey(CurDownloadJob, on_delete=models.CASCADE, related_name="files")
    s3_key = models.CharField(max_length=1024)
    local_path = models.CharField(max_length=1024)
    file_hash_sha256 = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField()
    downloaded_at = models.DateTimeField(auto_now_add=True)
    etl_status = models.CharField(choices=ETL_STATUS, default="pending", max_length=10)
