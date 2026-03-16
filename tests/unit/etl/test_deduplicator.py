import pandas as pd
from apps.etl.pipeline.deduplicator import deduplicate


def test_dedup_removes_existing_ids():
    df = pd.DataFrame({
        "line_item_id": ["a", "b", "c"],
        "billing_period": ["2025-01"] * 3,
    })
    result = deduplicate(df, existing_ids={"b"})
    assert set(result["line_item_id"]) == {"a", "c"}


def test_dedup_removes_within_file_duplicates():
    df = pd.DataFrame({
        "line_item_id": ["a", "a", "b"],
        "billing_period": ["2025-01"] * 3,
    })
    result = deduplicate(df, existing_ids=set())
    assert len(result) == 2


def test_dedup_empty_existing_ids_returns_all():
    df = pd.DataFrame({
        "line_item_id": ["x", "y", "z"],
        "billing_period": ["2025-01"] * 3,
    })
    result = deduplicate(df, existing_ids=set())
    assert len(result) == 3


def test_dedup_all_existing_returns_empty():
    df = pd.DataFrame({
        "line_item_id": ["a", "b"],
        "billing_period": ["2025-01"] * 2,
    })
    result = deduplicate(df, existing_ids={"a", "b"})
    assert len(result) == 0
