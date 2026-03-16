import pandas as pd
from apps.costs.models import DailyCostAggregate


def build_daily_trend(account_id=None, service=None, region=None,
                       start_date=None, end_date=None) -> dict:
    qs = DailyCostAggregate.objects.all()
    if account_id:
        qs = qs.filter(linked_account_id=account_id)
    if service:
        qs = qs.filter(service=service)
    if region:
        qs = qs.filter(region=region)
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    df = pd.DataFrame(list(qs.values("date", "service", "unblended_cost")))
    if df.empty:
        return {"data": [], "layout": {"title": "Daily Cost by Service"}}

    df["unblended_cost"] = df["unblended_cost"].astype(float)
    pivot = df.pivot_table(index="date", columns="service", values="unblended_cost", aggfunc="sum").fillna(0)
    traces = [
        {
            "type": "scatter", "mode": "lines+markers",
            "name": col,
            "x": [str(d) for d in pivot.index.tolist()],
            "y": [round(v, 4) for v in pivot[col].tolist()],
        }
        for col in pivot.columns
    ]
    return {
        "data": traces,
        "layout": {
            "title": "Daily Cost by Service",
            "xaxis": {"title": "Date"},
            "yaxis": {"title": "USD"},
            "hovermode": "x unified",
        },
    }
