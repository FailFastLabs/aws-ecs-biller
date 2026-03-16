import pytest


@pytest.mark.django_db
def test_ri_list_empty(api_client, db):
    resp = api_client.get("/api/v1/reservations/ris/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.django_db
def test_coverage_endpoint(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/reservations/coverage/?account_id=123456789012&billing_period=2025-01")
    assert resp.status_code == 200
    assert "results" in resp.json()


@pytest.mark.django_db
def test_sp_counterfactual_endpoint(api_client, loaded_line_items):
    resp = api_client.get("/api/v1/reservations/sp-counterfactual/?account_id=123456789012&billing_period=2025-01")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
