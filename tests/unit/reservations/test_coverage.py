import pytest


@pytest.mark.django_db
def test_coverage_returns_dataframe(loaded_line_items):
    from apps.reservations.services.coverage import compute_ri_coverage
    df = compute_ri_coverage("123456789012", "2025-01")
    assert hasattr(df, "columns")
    assert "coverage_pct" in df.columns
    assert "utilization_pct" in df.columns


@pytest.mark.django_db
def test_coverage_pct_between_0_and_1(loaded_line_items):
    from apps.reservations.services.coverage import compute_ri_coverage
    df = compute_ri_coverage("123456789012", "2025-01")
    if not df.empty:
        assert (df["coverage_pct"] >= 0).all()
        assert (df["coverage_pct"] <= 1).all()


@pytest.mark.django_db
def test_coverage_empty_for_unknown_account(db):
    from apps.reservations.services.coverage import compute_ri_coverage
    df = compute_ri_coverage("999999999999", "2025-01")
    assert df.empty
