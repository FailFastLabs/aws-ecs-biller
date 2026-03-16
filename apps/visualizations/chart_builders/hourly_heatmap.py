import pandas as pd
from apps.costs.models import HourlyCostAggregate


def build_hourly_heatmap(account_id=None, service=None, region=None) -> dict:
    qs = HourlyCostAggregate.objects.all()
    if account_id:
        qs = qs.filter(linked_account_id=account_id)
    if service:
        qs = qs.filter(service=service)
    if region:
        qs = qs.filter(region=region)

    df = pd.DataFrame(list(qs.values("hour", "unblended_cost")))
    if df.empty:
        return {"data": [], "layout": {"title": "Average Hourly Cost"}}

    df["unblended_cost"] = df["unblended_cost"].astype(float)
    df["hour_of_day"] = pd.to_datetime(df["hour"]).dt.hour
    df["day_of_week"] = pd.to_datetime(df["hour"]).dt.dayofweek
    pivot = df.pivot_table(index="day_of_week", columns="hour_of_day",
                            values="unblended_cost", aggfunc="mean").fillna(0)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return {
        "data": [{
            "type": "heatmap",
            "z": [[round(v, 4) for v in row] for row in pivot.values.tolist()],
            "x": list(range(24)),
            "y": [days[i] for i in pivot.index],
            "colorscale": "Blues",
        }],
        "layout": {
            "title": "Average Hourly Cost (Hour × Day)",
            "xaxis": {"title": "Hour of Day"},
            "yaxis": {"title": "Day of Week"},
        },
    }
