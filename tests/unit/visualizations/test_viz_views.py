"""Tests for visualization API views."""
import pytest
from datetime import date, datetime, timezone as dt_tz
from decimal import Decimal


@pytest.mark.django_db
def test_daily_trend_view(api_client):
    resp = api_client.get("/api/v1/viz/daily-trend/")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_hourly_heatmap_view(api_client):
    resp = api_client.get("/api/v1/viz/hourly-heatmap/")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_service_breakdown_view(api_client):
    resp = api_client.get("/api/v1/viz/service-breakdown/?billing_period=2025-01")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_ri_coverage_chart_view(api_client):
    resp = api_client.get("/api/v1/viz/ri-coverage/?account_id=123456789012&billing_period=2025-01")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_forecast_chart_view(api_client):
    resp = api_client.get("/api/v1/viz/forecast-chart/?forecast_run_id=0")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_anomaly_chart_view(api_client):
    resp = api_client.get(
        "/api/v1/viz/anomaly-chart/?account_id=123456789012"
        "&service=AmazonEC2&region=us-east-1"
        "&start=2025-01-01&end=2025-02-01"
    )
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_split_sunburst_view(api_client):
    resp = api_client.get("/api/v1/viz/split-sunburst/?rule_id=0&billing_period=2025-01")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.django_db
def test_spot_vs_od_view(api_client):
    resp = api_client.get("/api/v1/viz/spot-vs-od/?region=us-east-1&instance_type=m5.large")
    assert resp.status_code == 200
    assert "data" in resp.json()
