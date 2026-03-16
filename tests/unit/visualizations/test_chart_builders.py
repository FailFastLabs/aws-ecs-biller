"""Unit tests for all chart builder functions."""
import pytest
from datetime import date, datetime, timezone as dt_tz
from decimal import Decimal
from django.utils import timezone

from tests.factories.costs import DailyAggFactory, HourlyAggFactory, LineItemFactory
from tests.factories.accounts import AwsAccountFactory


# ──────────────────────────────────────────────────────────────
# daily_trend
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_daily_trend_empty():
    from apps.visualizations.chart_builders.daily_trend import build_daily_trend
    result = build_daily_trend()
    assert result["data"] == []


@pytest.mark.django_db
def test_daily_trend_with_data():
    from apps.visualizations.chart_builders.daily_trend import build_daily_trend
    DailyAggFactory(date=date(2025, 1, 1), service="AmazonEC2", unblended_cost=100.0)
    DailyAggFactory(date=date(2025, 1, 2), service="AmazonEC2", unblended_cost=120.0)
    DailyAggFactory(date=date(2025, 1, 1), service="AmazonS3", unblended_cost=20.0)
    result = build_daily_trend()
    assert len(result["data"]) >= 1
    assert "layout" in result
    names = {t["name"] for t in result["data"]}
    assert "AmazonEC2" in names


@pytest.mark.django_db
def test_daily_trend_with_filters():
    from apps.visualizations.chart_builders.daily_trend import build_daily_trend
    DailyAggFactory(
        date=date(2025, 1, 1), service="AmazonEC2",
        region="us-east-1", linked_account_id="111111111111", unblended_cost=50.0,
    )
    DailyAggFactory(
        date=date(2025, 1, 1), service="AmazonS3",
        region="us-west-2", linked_account_id="222222222222", unblended_cost=10.0,
    )
    result = build_daily_trend(
        account_id="111111111111", service="AmazonEC2",
        region="us-east-1",
        start_date=date(2025, 1, 1), end_date=date(2025, 1, 31),
    )
    assert len(result["data"]) == 1
    assert result["data"][0]["name"] == "AmazonEC2"


# ──────────────────────────────────────────────────────────────
# service_breakdown
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_service_breakdown_empty():
    from apps.visualizations.chart_builders.service_breakdown import build_service_breakdown
    result = build_service_breakdown("2025-01")
    assert result["data"] == []


@pytest.mark.django_db
def test_service_breakdown_with_data():
    from apps.visualizations.chart_builders.service_breakdown import build_service_breakdown
    DailyAggFactory(date=date(2025, 1, 5), service="AmazonEC2", unblended_cost=200.0)
    DailyAggFactory(date=date(2025, 1, 5), service="AmazonRDS", unblended_cost=50.0)
    result = build_service_breakdown("2025-01")
    assert len(result["data"]) >= 1
    assert all(t["type"] == "bar" for t in result["data"])


@pytest.mark.django_db
def test_service_breakdown_account_filter():
    from apps.visualizations.chart_builders.service_breakdown import build_service_breakdown
    DailyAggFactory(
        date=date(2025, 1, 3), service="AmazonEC2",
        linked_account_id="333333333333", unblended_cost=100.0,
    )
    result = build_service_breakdown("2025-01", account_id="999999999999")
    assert result["data"] == []


# ──────────────────────────────────────────────────────────────
# hourly_heatmap
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_hourly_heatmap_empty():
    from apps.visualizations.chart_builders.hourly_heatmap import build_hourly_heatmap
    result = build_hourly_heatmap()
    assert result["data"] == []


@pytest.mark.django_db
def test_hourly_heatmap_with_data():
    from apps.visualizations.chart_builders.hourly_heatmap import build_hourly_heatmap
    h = datetime(2025, 1, 6, 14, 0, 0, tzinfo=dt_tz.utc)  # Monday 14:00
    HourlyAggFactory(hour=h, service="AmazonEC2", region="us-east-1", unblended_cost=5.0)
    result = build_hourly_heatmap()
    assert len(result["data"]) == 1
    assert result["data"][0]["type"] == "heatmap"


@pytest.mark.django_db
def test_hourly_heatmap_with_filters():
    from apps.visualizations.chart_builders.hourly_heatmap import build_hourly_heatmap
    h = datetime(2025, 1, 6, 10, 0, 0, tzinfo=dt_tz.utc)
    HourlyAggFactory(hour=h, service="AmazonEC2", region="us-east-1", unblended_cost=3.0)
    HourlyAggFactory(hour=h, service="AmazonS3", region="us-west-2", unblended_cost=1.0)
    result = build_hourly_heatmap(service="AmazonEC2", region="us-east-1")
    assert result["data"][0]["type"] == "heatmap"


# ──────────────────────────────────────────────────────────────
# spot_prices
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_spot_vs_od_empty():
    from apps.visualizations.chart_builders.spot_prices import build_spot_vs_od_chart
    result = build_spot_vs_od_chart("us-east-1", "m5.large")
    assert result["data"] == []


@pytest.mark.django_db
def test_spot_vs_od_with_data():
    from apps.visualizations.chart_builders.spot_prices import build_spot_vs_od_chart
    from apps.costs.models import SpotPriceHistory, InstancePricing
    ts1 = datetime(2025, 1, 1, 0, 0, tzinfo=dt_tz.utc)
    ts2 = datetime(2025, 1, 1, 1, 0, tzinfo=dt_tz.utc)
    SpotPriceHistory.objects.create(
        region="us-east-1", instance_type="m5.large",
        availability_zone="us-east-1a", timestamp=ts1, spot_price=Decimal("0.04"),
    )
    SpotPriceHistory.objects.create(
        region="us-east-1", instance_type="m5.large",
        availability_zone="us-east-1a", timestamp=ts2, spot_price=Decimal("0.05"),
    )
    InstancePricing.objects.create(
        region="us-east-1", instance_type="m5.large",
        od_hourly=Decimal("0.096"),
        convertible_1yr_hourly=Decimal("0.060"),
        convertible_3yr_hourly=Decimal("0.045"),
        standard_1yr_hourly=Decimal("0.058"),
        standard_3yr_hourly=Decimal("0.040"),
        effective_date="2025-01-01",
    )
    result = build_spot_vs_od_chart("us-east-1", "m5.large")
    assert len(result["data"]) >= 1
    names = {t["name"] for t in result["data"]}
    assert "On-Demand" in names


@pytest.mark.django_db
def test_spot_vs_od_no_pricing():
    from apps.visualizations.chart_builders.spot_prices import build_spot_vs_od_chart
    from apps.costs.models import SpotPriceHistory
    ts = datetime(2025, 1, 1, 0, 0, tzinfo=dt_tz.utc)
    SpotPriceHistory.objects.create(
        region="eu-west-1", instance_type="t3.medium",
        availability_zone="eu-west-1a", timestamp=ts, spot_price=Decimal("0.02"),
    )
    result = build_spot_vs_od_chart("eu-west-1", "t3.medium")
    # Should have spot trace but no On-Demand trace
    assert any(t["type"] == "scatter" for t in result["data"])
    names = {t["name"] for t in result["data"]}
    assert "On-Demand" not in names


# ──────────────────────────────────────────────────────────────
# anomaly_chart
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_anomaly_chart_empty():
    from apps.visualizations.chart_builders.anomaly_chart import build_anomaly_chart
    from datetime import datetime, timezone as dt_tz
    start = datetime(2025, 1, 1, tzinfo=dt_tz.utc)
    end = datetime(2025, 1, 31, tzinfo=dt_tz.utc)
    result = build_anomaly_chart("123456789012", "AmazonEC2", "us-east-1", start, end)
    assert result["data"] == []


@pytest.mark.django_db
def test_anomaly_chart_with_data():
    from apps.visualizations.chart_builders.anomaly_chart import build_anomaly_chart
    from apps.anomalies.models import AnomalyDetectionRun, CostAnomaly
    from datetime import datetime, timezone as dt_tz
    h = datetime(2025, 1, 10, 12, 0, tzinfo=dt_tz.utc)
    HourlyAggFactory(
        hour=h, service="AmazonEC2", region="us-east-1",
        linked_account_id="123456789012", unblended_cost=500.0,
    )
    account = AwsAccountFactory()
    run = AnomalyDetectionRun.objects.create(
        account=account, grain="hourly", method="zscore",
        window_hours=168, sigma_threshold=3.5, min_cost_delta=5.0,
    )
    CostAnomaly.objects.create(
        detection_run=run, service="AmazonEC2", region="us-east-1",
        usage_type="BoxUsage", linked_account_id="123456789012",
        period_start=h, period_end=h,
        direction="spike", baseline_cost=100.0, observed_cost=500.0,
        pct_change=400.0, z_score=5.0,
    )
    start = datetime(2025, 1, 1, tzinfo=dt_tz.utc)
    end = datetime(2025, 1, 31, tzinfo=dt_tz.utc)
    result = build_anomaly_chart("123456789012", "AmazonEC2", "us-east-1", start, end)
    assert len(result["data"]) == 2
    types = {t["type"] for t in result["data"]}
    assert "scatter" in types


# ──────────────────────────────────────────────────────────────
# ri_coverage
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_ri_coverage_empty():
    from apps.visualizations.chart_builders.ri_coverage import build_ri_coverage
    result = build_ri_coverage("123456789012", "2025-01")
    assert result["data"] == []


@pytest.mark.django_db
def test_ri_coverage_with_data():
    from apps.visualizations.chart_builders.ri_coverage import build_ri_coverage
    arn = "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-cov"
    LineItemFactory(
        billing_period="2025-01", linked_account_id="123456789012",
        line_item_type="RIFee", reservation_arn=arn,
        instance_type="m5.large", region="us-east-1", offering_class="standard",
        normalized_usage_amount=744.0, unblended_cost=50.0,
        reservation_unused_quantity=0.0, reservation_unused_recurring_fee=0.0,
    )
    LineItemFactory(
        billing_period="2025-01", linked_account_id="123456789012",
        line_item_type="DiscountedUsage", reservation_arn=arn,
        instance_type="m5.large", region="us-east-1",
        normalized_usage_amount=744.0, usage_quantity=744.0,
    )
    LineItemFactory(
        billing_period="2025-01", linked_account_id="123456789012",
        line_item_type="Usage", instance_type="m5.large",
        region="us-east-1", unblended_cost=0.0, usage_quantity=744.0,
    )
    result = build_ri_coverage("123456789012", "2025-01")
    assert isinstance(result["data"], list)


# ──────────────────────────────────────────────────────────────
# split_sunburst
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_split_sunburst_empty():
    from apps.visualizations.chart_builders.split_sunburst import build_split_sunburst
    result = build_split_sunburst(999, "2025-01")
    assert result["data"] == []


@pytest.mark.django_db
def test_split_sunburst_with_data():
    from apps.visualizations.chart_builders.split_sunburst import build_split_sunburst
    from apps.splitting.models import SplitResult
    from tests.factories.splitting import SplittingRuleFactory
    rule = SplittingRuleFactory()
    hour = datetime(2025, 1, 5, 10, 0, tzinfo=dt_tz.utc)
    for tenant, cost in [("backend", "40.0"), ("frontend", "35.0"), ("data", "25.0")]:
        SplitResult.objects.create(
            splitting_rule=rule, billing_period="2025-01",
            hour=hour, region="us-east-1", usage_type="BoxUsage",
            tenant_tag_value=tenant, original_cost="100.0",
            allocated_cost=cost, allocation_weight="0.33000000",
        )
    result = build_split_sunburst(rule.id, "2025-01")
    assert result["data"][0]["type"] == "sunburst"
    assert len(result["data"][0]["labels"]) == 4  # root + 3 tenants


# ──────────────────────────────────────────────────────────────
# forecast_chart
# ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_forecast_chart_empty():
    from apps.visualizations.chart_builders.forecast_chart import build_forecast_chart
    result = build_forecast_chart(99999)
    assert result["data"] == []


@pytest.mark.django_db
def test_forecast_chart_with_data():
    from apps.visualizations.chart_builders.forecast_chart import build_forecast_chart
    from apps.forecasting.models import ForecastRun, ForecastPoint
    account = AwsAccountFactory()
    run = ForecastRun.objects.create(
        account=account, grain="hourly", service="AmazonEC2", region="us-east-1",
        usage_type="BoxUsage", training_start=date(2025, 1, 1),
        training_end=date(2025, 1, 28), forecast_horizon=24,
    )
    ForecastPoint.objects.create(
        forecast_run=run,
        timestamp=datetime(2025, 1, 29, 0, 0, tzinfo=dt_tz.utc),
        predicted_cost=Decimal("100.0"),
        lower_bound=Decimal("80.0"),
        upper_bound=Decimal("120.0"),
        actual_cost=Decimal("105.0"),
    )
    result = build_forecast_chart(run.id)
    assert len(result["data"]) == 4  # predicted, upper, lower, actual
    assert result["data"][0]["name"] == "Predicted"
