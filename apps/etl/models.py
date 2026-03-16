from django.db import models


class EtlRun(models.Model):
    STATUS_CHOICES = [("pending","pending"),("running","running"),("success","success"),("failed","failed")]
    cur_file = models.ForeignKey("ingestion.CurFile", on_delete=models.CASCADE, related_name="etl_runs")
    rows_read = models.BigIntegerField(default=0)
    rows_after_dedup = models.BigIntegerField(default=0)
    rows_loaded = models.BigIntegerField(default=0)
    duration_seconds = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_detail = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
