import pytest


@pytest.mark.django_db
def test_cost_by_service_returns_200(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/costs/by-service/?billing_period=2025-01")
    assert resp.status_code == 200
    data = resp.json()
    services = [r["service"] for r in data["results"]]
    assert "AmazonEC2" in services


@pytest.mark.django_db
def test_daily_trend_chart_has_correct_structure(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/viz/daily-trend/?start_date=2025-01-01&end_date=2025-01-31")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "layout" in body
    assert len(body["data"]) > 0
    trace = body["data"][0]
    assert trace["type"] == "scatter"


@pytest.mark.django_db
def test_top_n_returns_correct_count(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/costs/top-n/?n=3&group_by=service&billing_period=2025-01")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 3


@pytest.mark.django_db
def test_line_items_endpoint_paginated(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/costs/line-items/?billing_period=2025-01")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body
    assert body["count"] > 0


@pytest.mark.django_db
def test_cost_by_region_returns_results(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/costs/by-region/?billing_period=2025-01")
    assert resp.status_code == 200
    regions = [r["region"] for r in resp.json()["results"]]
    assert "us-east-1" in regions


@pytest.mark.django_db
def test_hourly_heatmap_returns_heatmap(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/viz/hourly-heatmap/")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    if body["data"]:
        assert body["data"][0]["type"] == "heatmap"


@pytest.mark.django_db
def test_invalid_top_n_group_by_returns_400(api_client, db):
    resp = api_client.get("/api/v1/costs/top-n/?n=5&group_by=INVALID")
    assert resp.status_code == 400
