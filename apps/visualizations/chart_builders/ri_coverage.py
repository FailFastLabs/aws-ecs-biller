def build_ri_coverage(account_id: str, billing_period: str) -> dict:
    from apps.reservations.services.coverage import compute_ri_coverage
    df = compute_ri_coverage(account_id, billing_period)
    if df.empty:
        return {"data": [], "layout": {"title": "RI Coverage"}}

    instance_types = df["instance_type"].unique().tolist()
    traces = [
        {
            "type": "bar",
            "name": it,
            "x": ["coverage_pct", "utilization_pct"],
            "y": [
                round(float(df[df["instance_type"] == it]["coverage_pct"].mean()), 4),
                round(float(df[df["instance_type"] == it]["utilization_pct"].mean()), 4),
            ],
        }
        for it in instance_types
    ]
    return {
        "data": traces,
        "layout": {"title": f"RI Coverage & Utilization ({billing_period})", "barmode": "group"},
    }
