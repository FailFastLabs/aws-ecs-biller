from django.db import models


class LineItem(models.Model):
    # Identity
    line_item_id = models.CharField(max_length=256, db_index=True)
    time_interval = models.CharField(max_length=64, blank=True)
    billing_period = models.CharField(max_length=20, db_index=True)

    # Bill
    bill_type = models.CharField(max_length=64, blank=True)
    payer_account_id = models.CharField(max_length=12, blank=True, db_index=True)
    invoice_id = models.CharField(max_length=64, blank=True)

    # Line item dimensions
    linked_account_id = models.CharField(max_length=12, blank=True, db_index=True)
    linked_account_name = models.CharField(max_length=128, blank=True)
    usage_start = models.DateTimeField(null=True, blank=True, db_index=True)
    usage_end = models.DateTimeField(null=True, blank=True)
    line_item_type = models.CharField(max_length=64, blank=True, db_index=True)
    service = models.CharField(max_length=128, blank=True, db_index=True)
    usage_type = models.CharField(max_length=256, blank=True, db_index=True)
    operation = models.CharField(max_length=128, blank=True)
    resource_id = models.CharField(max_length=512, blank=True)
    availability_zone = models.CharField(max_length=32, blank=True)

    # Usage & cost
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    unblended_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    blended_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    net_unblended_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    normalization_factor = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    normalized_usage_amount = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    description = models.TextField(blank=True)
    currency_code = models.CharField(max_length=8, blank=True, default="USD")

    # Pricing
    public_on_demand_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    pricing_term = models.CharField(max_length=64, blank=True)
    pricing_unit = models.CharField(max_length=64, blank=True)
    offering_class = models.CharField(max_length=32, blank=True)
    purchase_option = models.CharField(max_length=64, blank=True)
    lease_contract_length = models.CharField(max_length=16, blank=True)

    # Product
    region = models.CharField(max_length=64, blank=True, db_index=True)
    instance_type = models.CharField(max_length=64, blank=True, db_index=True)
    instance_family = models.CharField(max_length=64, blank=True)
    product_family = models.CharField(max_length=128, blank=True)
    service_code = models.CharField(max_length=128, blank=True)
    product_sku = models.CharField(max_length=64, blank=True)
    product_json = models.JSONField(null=True, blank=True)

    # Reservation
    reservation_arn = models.CharField(max_length=512, blank=True, db_index=True)
    reservation_effective_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    reservation_amortized_upfront_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    reservation_recurring_fee = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    reservation_unused_quantity = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    reservation_unused_recurring_fee = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    reservation_norm_units = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    reservation_count = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reservation_start = models.CharField(max_length=32, blank=True)
    reservation_end = models.CharField(max_length=32, blank=True)
    reservation_subscription_id = models.CharField(max_length=64, blank=True)

    # Savings Plan
    savings_plan_arn = models.CharField(max_length=512, blank=True, db_index=True)
    sp_effective_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    sp_offering_type = models.CharField(max_length=64, blank=True)
    sp_payment_option = models.CharField(max_length=64, blank=True)
    sp_purchase_term = models.CharField(max_length=16, blank=True)
    sp_region = models.CharField(max_length=64, blank=True)
    sp_used_commitment = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    sp_total_commitment = models.DecimalField(max_digits=20, decimal_places=6, default=0)

    # Split
    split_cost = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    split_actual_usage = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    split_usage_ratio = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    split_parent_resource_id = models.CharField(max_length=512, blank=True)

    # Tags & misc
    tags = models.JSONField(default=dict)
    cost_category = models.CharField(max_length=256, blank=True)
    total_discount = models.DecimalField(max_digits=20, decimal_places=6, default=0)

    # Billing period start/end
    billing_period_start = models.DateTimeField(null=True, blank=True)
    billing_period_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["line_item_id", "billing_period"], name="uq_li_bp")
        ]
        indexes = [
            models.Index(fields=["linked_account_id", "billing_period"]),
            models.Index(fields=["service", "region", "billing_period"]),
            models.Index(fields=["usage_start"]),
        ]

    def __str__(self):
        return f"{self.line_item_id} ({self.billing_period})"


class DailyCostAggregate(models.Model):
    date = models.DateField(db_index=True)
    linked_account_id = models.CharField(max_length=12, db_index=True)
    service = models.CharField(max_length=128, db_index=True)
    region = models.CharField(max_length=64, db_index=True)
    usage_type = models.CharField(max_length=256)
    line_item_type = models.CharField(max_length=64)
    unblended_cost = models.DecimalField(max_digits=20, decimal_places=6)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=6)

    class Meta:
        unique_together = [
            ("date", "linked_account_id", "service", "region", "usage_type", "line_item_type")
        ]

    def __str__(self):
        return f"{self.date} {self.service} {self.region}"


class HourlyCostAggregate(models.Model):
    hour = models.DateTimeField(db_index=True)
    linked_account_id = models.CharField(max_length=12, db_index=True)
    service = models.CharField(max_length=128, db_index=True)
    region = models.CharField(max_length=64, db_index=True)
    usage_type = models.CharField(max_length=256)
    line_item_type = models.CharField(max_length=64)
    unblended_cost = models.DecimalField(max_digits=20, decimal_places=6)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=6)

    class Meta:
        unique_together = [
            ("hour", "linked_account_id", "service", "region", "usage_type", "line_item_type")
        ]


class EdpDiscount(models.Model):
    service = models.CharField(max_length=128, db_index=True)
    region = models.CharField(max_length=64, db_index=True)
    discount_pct = models.DecimalField(max_digits=6, decimal_places=3)
    effective_date = models.DateField()
    source = models.CharField(max_length=32, default="manual")

    class Meta:
        unique_together = [("service", "region", "effective_date")]


class SpotPriceHistory(models.Model):
    region = models.CharField(max_length=64, db_index=True)
    instance_type = models.CharField(max_length=64, db_index=True)
    availability_zone = models.CharField(max_length=32)
    timestamp = models.DateTimeField(db_index=True)
    spot_price = models.DecimalField(max_digits=10, decimal_places=6)

    class Meta:
        unique_together = [("region", "instance_type", "availability_zone", "timestamp")]
        indexes = [models.Index(fields=["region", "instance_type", "timestamp"])]


class InstancePricing(models.Model):
    region = models.CharField(max_length=64, db_index=True)
    instance_type = models.CharField(max_length=64, db_index=True)
    od_hourly = models.DecimalField(max_digits=10, decimal_places=6)
    convertible_1yr_hourly = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    convertible_3yr_hourly = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    standard_1yr_hourly = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    standard_3yr_hourly = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    effective_date = models.DateField()
    source = models.CharField(max_length=32, default="manual")

    class Meta:
        unique_together = [("region", "instance_type", "effective_date")]
