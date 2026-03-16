from django.db import models


class AnomalyDetectionRun(models.Model):
    account = models.ForeignKey("accounts.AwsAccount", on_delete=models.CASCADE)
    grain = models.CharField(max_length=16)
    method = models.CharField(max_length=32)
    window_hours = models.IntegerField()
    sigma_threshold = models.FloatField(default=3.5)
    min_cost_delta = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)
    created_at = models.DateTimeField(auto_now_add=True)


class CostAnomaly(models.Model):
    DIRECTION = [("spike", "spike"), ("drop", "drop")]
    detection_run = models.ForeignKey(AnomalyDetectionRun, on_delete=models.CASCADE, related_name="anomalies")
    service = models.CharField(max_length=128, db_index=True)
    region = models.CharField(max_length=64)
    usage_type = models.CharField(max_length=256)
    linked_account_id = models.CharField(max_length=12)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    direction = models.CharField(choices=DIRECTION, max_length=8)
    baseline_cost = models.DecimalField(max_digits=20, decimal_places=6)
    observed_cost = models.DecimalField(max_digits=20, decimal_places=6)
    pct_change = models.FloatField()
    z_score = models.FloatField(null=True, blank=True)
    chronos_sigma = models.FloatField(null=True, blank=True)
    detected_by = models.CharField(max_length=32, default="ensemble")
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
