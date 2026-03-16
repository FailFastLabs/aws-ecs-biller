from django.db import models


class SplittingRule(models.Model):
    STRATEGIES = [
        ("equal", "equal"),
        ("proportional_usage", "proportional_usage"),
        ("custom_weight", "custom_weight"),
    ]
    name = models.CharField(max_length=128)
    service = models.CharField(max_length=128)
    region = models.CharField(max_length=64)
    split_by_tag_key = models.CharField(max_length=128)
    weight_strategy = models.CharField(choices=STRATEGIES, max_length=32)
    custom_weights = models.JSONField(default=dict)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SplitResult(models.Model):
    splitting_rule = models.ForeignKey(SplittingRule, on_delete=models.CASCADE, related_name="results")
    billing_period = models.CharField(max_length=20, db_index=True)
    hour = models.DateTimeField(db_index=True)
    region = models.CharField(max_length=64, db_index=True)
    usage_type = models.CharField(max_length=256, db_index=True)
    tenant_tag_value = models.CharField(max_length=256, db_index=True)
    original_cost = models.DecimalField(max_digits=20, decimal_places=10)
    allocated_cost = models.DecimalField(max_digits=20, decimal_places=10)
    allocation_weight = models.DecimalField(max_digits=10, decimal_places=8)

    class Meta:
        unique_together = [("splitting_rule", "hour", "region", "usage_type", "tenant_tag_value")]
