import pytest


@pytest.mark.django_db
def test_sp_counterfactual_returns_dict(loaded_line_items):
    from apps.reservations.services.sp_counterfactual import compute_sp_counterfactual
    result = compute_sp_counterfactual("123456789012", "2025-01")
    assert isinstance(result, dict)


@pytest.mark.django_db
def test_sp_counterfactual_empty_for_unknown(db):
    from apps.reservations.services.sp_counterfactual import compute_sp_counterfactual
    result = compute_sp_counterfactual("999999999999", "2025-01")
    assert result == {}
