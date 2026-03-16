import pytest


@pytest.mark.django_db
def test_anomaly_list_empty(api_client, db):
    resp = api_client.get("/api/v1/anomalies/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_anomaly_summary(api_client, db):
    resp = api_client.get("/api/v1/anomalies/summary/")
    assert resp.status_code == 200
    body = resp.json()
    assert "spike_count" in body
    assert "drop_count" in body


@pytest.mark.django_db
def test_run_detection_endpoint(api_client, loaded_line_items):
    resp = api_client.post("/api/v1/anomalies/runs/", data={
        "account_id": "123456789012",
        "service": "AmazonEC2",
        "region": "us-east-1",
        "grain": "daily",
        "sigma_threshold": 2.5,
        "min_cost_delta": 5.0,
    }, format="json")
    assert resp.status_code == 201
    assert "detected" in resp.json()
