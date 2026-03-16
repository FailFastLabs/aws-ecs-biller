from django.db import models


class AwsAccount(models.Model):
    account_id = models.CharField(max_length=12, unique=True)
    account_name = models.CharField(max_length=128)
    iam_role_arn = models.CharField(max_length=256, blank=True)
    is_payer = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["account_id"]

    def __str__(self):
        return f"{self.account_name} ({self.account_id})"


class CurManifest(models.Model):
    TIME_UNIT_CHOICES = [("HOURLY", "HOURLY"), ("DAILY", "DAILY")]
    COMPRESSION_CHOICES = [("GZIP", "GZIP"), ("Parquet", "Parquet")]

    account = models.ForeignKey(AwsAccount, on_delete=models.CASCADE, related_name="manifests")
    s3_bucket = models.CharField(max_length=256)
    s3_prefix = models.CharField(max_length=512)
    report_name = models.CharField(max_length=256)
    time_unit = models.CharField(choices=TIME_UNIT_CHOICES, max_length=10)
    compression = models.CharField(choices=COMPRESSION_CHOICES, max_length=10)
    aws_region = models.CharField(max_length=32)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.report_name} ({self.s3_bucket})"
