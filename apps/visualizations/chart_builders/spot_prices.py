import pandas as pd
from apps.costs.models import SpotPriceHistory, InstancePricing


def build_spot_vs_od_chart(region: str, instance_type: str) -> dict:
    try:
        pricing = InstancePricing.objects.filter(
            region=region, instance_type=instance_type
        ).latest("effective_date")
        od_rate = float(pricing.od_hourly)
    except InstancePricing.DoesNotExist:
        od_rate = None

    spots = list(SpotPriceHistory.objects.filter(
        region=region, instance_type=instance_type
    ).order_by("timestamp").values("timestamp", "spot_price", "availability_zone"))

    if not spots:
        return {"data": [], "layout": {"title": "Spot vs On-Demand"}}

    df = pd.DataFrame(spots)
    df["spot_price"] = df["spot_price"].astype(float)
    traces = []
    for az in df["availability_zone"].unique():
        az_df = df[df["availability_zone"] == az]
        traces.append({
            "type": "scatter", "mode": "lines",
            "name": az,
            "x": [str(t) for t in az_df["timestamp"].tolist()],
            "y": az_df["spot_price"].tolist(),
        })

    if od_rate:
        first_ts = str(df["timestamp"].iloc[0])
        last_ts = str(df["timestamp"].iloc[-1])
        traces.append({
            "type": "scatter", "mode": "lines",
            "name": "On-Demand",
            "x": [first_ts, last_ts],
            "y": [od_rate, od_rate],
            "line": {"dash": "dash", "color": "red"},
        })

    return {
        "data": traces,
        "layout": {
            "title": f"Spot vs On-Demand: {instance_type} in {region}",
            "xaxis": {"title": "Time"},
            "yaxis": {"title": "$/hr"},
        },
    }
