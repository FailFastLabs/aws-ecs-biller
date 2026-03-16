import pandas as pd
import pytest
from apps.etl.pipeline.normalizer import normalize_schema


def test_normalize_renames_columns():
    raw = pd.DataFrame({
        "identity_line_item_id": ["li-001"],
        "line_item_unblended_cost": ["1.234567"],
        "line_item_usage_start_date": ["2025-01-01T00:00:00Z"],
        "bill_billing_period_start_date": ["2025-01-01T00:00:00Z"],
        "line_item_usage_account_id": ["123456789012"],
        "line_item_product_code": ["AmazonEC2"],
        "line_item_usage_amount": ["1.0"],
        "line_item_blended_cost": ["1.234567"],
    })
    result = normalize_schema(raw)
    assert "line_item_id" in result.columns
    assert "unblended_cost" in result.columns
    assert "usage_start" in result.columns
    assert pd.api.types.is_datetime64_any_dtype(result["usage_start"])
    assert result["billing_period"].iloc[0] == "2025-01"


def test_normalize_fills_zero_for_missing_cost():
    raw = pd.DataFrame({
        "identity_line_item_id": ["li-002"],
        "line_item_unblended_cost": [None],
        "line_item_usage_start_date": ["2025-01-01T00:00:00Z"],
        "bill_billing_period_start_date": ["2025-01-01T00:00:00Z"],
        "line_item_usage_account_id": ["123456789012"],
        "line_item_product_code": ["AmazonEC2"],
        "line_item_usage_amount": ["1.0"],
        "line_item_blended_cost": ["0"],
    })
    result = normalize_schema(raw)
    assert result["unblended_cost"].iloc[0] == 0.0


def test_normalize_parses_tags_json():
    raw = pd.DataFrame({"resource_tags": ['{"user:team":"backend","user:env":"prod"}']})
    result = normalize_schema(raw)
    assert result["tags"].iloc[0] == {"user:team": "backend", "user:env": "prod"}


def test_normalize_handles_malformed_tags():
    raw = pd.DataFrame({"resource_tags": ["not-valid-json"]})
    result = normalize_schema(raw)
    assert result["tags"].iloc[0] == {}


def test_normalize_handles_empty_tags():
    raw = pd.DataFrame({"resource_tags": [None]})
    result = normalize_schema(raw)
    assert result["tags"].iloc[0] == {}
