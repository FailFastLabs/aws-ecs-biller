import pandas as pd
from apps.etl.pipeline.validator import validate


def _base_row(**kwargs):
    row = {
        "line_item_id": "li-001",
        "billing_period": "2025-01",
        "usage_start": "2025-01-01",
        "service": "AmazonEC2",
        "linked_account_id": "123456789012",
        "unblended_cost": 1.0,
        "line_item_type": "Usage",
    }
    row.update(kwargs)
    return pd.DataFrame([row])


def test_validate_accepts_valid_row():
    df = _base_row()
    valid, rejected = validate(df)
    assert len(valid) == 1
    assert len(rejected) == 0


def test_validate_rejects_null_line_item_id():
    df = _base_row(line_item_id=None)
    valid, rejected = validate(df)
    assert len(valid) == 0
    assert len(rejected) == 1


def test_validate_rejects_negative_non_credit():
    df = _base_row(unblended_cost=-5.0, line_item_type="Usage")
    valid, rejected = validate(df)
    assert len(valid) == 0


def test_validate_allows_negative_credit():
    df = _base_row(unblended_cost=-100.0, line_item_type="Credit")
    valid, rejected = validate(df)
    assert len(valid) == 1


def test_validate_allows_negative_refund():
    df = _base_row(unblended_cost=-50.0, line_item_type="Refund")
    valid, rejected = validate(df)
    assert len(valid) == 1


def test_validate_rejects_null_service():
    df = _base_row(service=None)
    valid, rejected = validate(df)
    assert len(valid) == 0
