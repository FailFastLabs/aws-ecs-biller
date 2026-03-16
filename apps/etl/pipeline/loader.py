import pandas as pd


def _row_to_model_kwargs(row: dict) -> dict:
    from apps.costs.models import LineItem
    fields = {f.name for f in LineItem._meta.get_fields() if hasattr(f, 'column')}
    return {k: v for k, v in row.items() if k in fields and not (isinstance(v, float) and v != v)}


def bulk_load(df: pd.DataFrame, batch_size: int = 10_000) -> int:
    from apps.costs.models import LineItem
    records = df.to_dict("records")
    objs = []
    for rec in records:
        kwargs = _row_to_model_kwargs(rec)
        # Ensure required fields have defaults
        kwargs.setdefault("unblended_cost", 0)
        kwargs.setdefault("blended_cost", 0)
        kwargs.setdefault("net_unblended_cost", 0)
        kwargs.setdefault("usage_quantity", 0)
        kwargs.setdefault("tags", {})
        objs.append(LineItem(**kwargs))
    created = LineItem.objects.bulk_create(objs, batch_size=batch_size, ignore_conflicts=True)
    return len(created)
