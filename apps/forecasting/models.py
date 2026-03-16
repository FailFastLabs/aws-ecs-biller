from django.db import models


GROUPING_REGION = "region"
GROUPING_REGION_SERVICE = "region_service"
GROUPING_REGION_SERVICE_INSTANCE = "region_service_instance"

GROUPING_CHOICES = [
    (GROUPING_REGION, "Region"),
    (GROUPING_REGION_SERVICE, "Region + Service"),
    (GROUPING_REGION_SERVICE_INSTANCE, "Region + Service + Instance Type"),
]


class ForecastRun(models.Model):
    account = models.ForeignKey("accounts.AwsAccount", on_delete=models.CASCADE)
    grain = models.CharField(max_length=16)
    grouping_level = models.CharField(max_length=32, choices=GROUPING_CHOICES, default=GROUPING_REGION_SERVICE)
    service = models.CharField(max_length=128, blank=True)
    region = models.CharField(max_length=64, blank=True)
    instance_type = models.CharField(max_length=64, blank=True)
    usage_type = models.CharField(max_length=256, blank=True)
    training_start = models.DateField()
    training_end = models.DateField()
    forecast_horizon = models.IntegerField()
    model_name = models.CharField(max_length=64, default="chronos-t5-small")
    mae = models.FloatField(null=True, blank=True)
    mape = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        parts = [self.region]
        if self.service:
            parts.append(self.service)
        if self.instance_type:
            parts.append(self.instance_type)
        return f"ForecastRun {self.id} ({self.grain}, {'/'.join(parts)})"


class ForecastPoint(models.Model):
    forecast_run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="points")
    timestamp = models.DateTimeField(db_index=True)
    predicted_cost = models.DecimalField(max_digits=20, decimal_places=6)
    lower_bound = models.DecimalField(max_digits=20, decimal_places=6)
    upper_bound = models.DecimalField(max_digits=20, decimal_places=6)
    actual_cost = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)

    class Meta:
        unique_together = [("forecast_run", "timestamp")]
