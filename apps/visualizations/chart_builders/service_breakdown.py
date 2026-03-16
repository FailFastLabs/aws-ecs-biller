import pandas as pd
from apps.costs.models import DailyCostAggregate


def build_service_breakdown(billing_period: str, account_id=None) -> dict:
    qs = DailyCostAggregate.objects.filter(date__startswith=billing_period[:7])
    if account_id:
        qs = qs.filter(linked_account_id=account_id)
    df = pd.DataFrame(list(qs.values("date", "service", "unblended_cost")))
    if df.empty:
        return {"data": [], "layout": {"title": "Cost by Service"}}
    df["unblended_cost"] = df["unblended_cost"].astype(float)
    services = df["service"].unique()
    dates = sorted(df["date"].unique())
    traces = []
    for svc in services:
        sdf = df[df["service"] == svc].set_index("date")["unblended_cost"]
        traces.append({
            "type": "bar", "name": svc,
            "x": [str(d) for d in dates],
            "y": [round(float(sdf.get(d, 0)), 4) for d in dates],
        })
    return {
        "data": traces,
        "layout": {"title": f"Cost by Service ({billing_period})", "barmode": "stack"},
    }
