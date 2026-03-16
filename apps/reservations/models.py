from django.db import models


class ReservedInstance(models.Model):
    account = models.ForeignKey("accounts.AwsAccount", on_delete=models.CASCADE, related_name="reserved_instances")
    reservation_id = models.CharField(max_length=64, unique=True)
    reservation_arn = models.CharField(max_length=512, unique=True)
    instance_type = models.CharField(max_length=64, db_index=True)
    instance_family = models.CharField(max_length=64)
    normalized_units = models.FloatField()
    region = models.CharField(max_length=64)
    tenancy = models.CharField(max_length=32)
    platform = models.CharField(max_length=64)
    offering_class = models.CharField(max_length=32)
    offering_type = models.CharField(max_length=64)
    instance_count = models.IntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    fixed_price = models.DecimalField(max_digits=20, decimal_places=6)
    recurring_hourly_cost = models.DecimalField(max_digits=20, decimal_places=6)
    scope = models.CharField(max_length=32)
    state = models.CharField(max_length=32)

    def __str__(self):
        return f"{self.instance_type} x{self.instance_count} ({self.offering_class})"


class SavingsPlan(models.Model):
    account = models.ForeignKey("accounts.AwsAccount", on_delete=models.CASCADE, related_name="savings_plans")
    savings_plan_id = models.CharField(max_length=64, unique=True)
    savings_plan_arn = models.CharField(max_length=512)
    plan_type = models.CharField(max_length=32)
    commitment_hourly = models.DecimalField(max_digits=20, decimal_places=6)
    start_date = models.DateField()
    end_date = models.DateField()
    state = models.CharField(max_length=32)


class RiRecommendation(models.Model):
    account = models.ForeignKey("accounts.AwsAccount", on_delete=models.CASCADE)
    generated_at = models.DateTimeField(auto_now_add=True)
    recommendation_type = models.CharField(max_length=32)
    instance_type = models.CharField(max_length=64)
    region = models.CharField(max_length=64)
    platform = models.CharField(max_length=64, blank=True)
    quantity = models.IntegerField()
    estimated_monthly_savings = models.DecimalField(max_digits=20, decimal_places=2)
    break_even_months = models.FloatField(null=True, blank=True)
    analysis_window_days = models.IntegerField(default=30)
    confidence_score = models.FloatField()
    detail_json = models.JSONField(default=dict)
