def build_anomaly_chart(account_id: str, service: str, region: str, start, end) -> dict:
    from apps.costs.models import HourlyCostAggregate
    from apps.anomalies.models import CostAnomaly
    import pandas as pd

    qs = HourlyCostAggregate.objects.filter(
        linked_account_id=account_id, service=service, region=region,
        hour__range=(start, end),
    ).order_by("hour").values("hour", "unblended_cost")
    df = pd.DataFrame(list(qs))
    if df.empty:
        return {"data": [], "layout": {"title": "Anomaly Chart"}}
    df["unblended_cost"] = df["unblended_cost"].astype(float)
    x = [str(h) for h in df["hour"].tolist()]
    y = df["unblended_cost"].tolist()

    anomalies = list(CostAnomaly.objects.filter(
        linked_account_id=account_id, service=service, region=region,
        period_start__range=(start, end),
    ).values("period_start", "observed_cost", "direction"))

    ax = [str(a["period_start"]) for a in anomalies]
    ay = [float(a["observed_cost"]) for a in anomalies]
    colors = ["red" if a["direction"] == "spike" else "blue" for a in anomalies]

    return {
        "data": [
            {"type": "scatter", "mode": "lines", "name": "Cost", "x": x, "y": y},
            {"type": "scatter", "mode": "markers", "name": "Anomaly", "x": ax, "y": ay,
             "marker": {"color": colors, "size": 10, "symbol": "x"}},
        ],
        "layout": {"title": f"Anomalies: {service} {region}", "xaxis": {"title": "Hour"}, "yaxis": {"title": "USD"}},
    }
