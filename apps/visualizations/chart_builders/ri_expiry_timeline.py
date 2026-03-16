from collections import defaultdict


def build_ri_expiry_timeline(account_id: str = "") -> dict:
    from apps.reservations.models import ReservedInstance, SavingsPlan

    ri_qs = ReservedInstance.objects.filter(state="active")
    sp_qs = SavingsPlan.objects.filter(state="active")
    if account_id:
        ri_qs = ri_qs.filter(account__account_id=account_id)
        sp_qs = sp_qs.filter(account__account_id=account_id)

    # Group RIs by (end_date, instance_family) → sum $/hr
    ri_by_date_family: dict = defaultdict(float)
    families = set()
    for ri in ri_qs.values("end_date", "instance_family", "recurring_hourly_cost", "instance_count"):
        key = (str(ri["end_date"]), ri["instance_family"] or "other")
        hourly = float(ri["recurring_hourly_cost"] or 0) * (ri["instance_count"] or 1)
        ri_by_date_family[key] += hourly
        families.add(ri["instance_family"] or "other")

    # Group SPs by end_date → sum commitment_hourly
    sp_by_date: dict = defaultdict(float)
    for sp in sp_qs.values("end_date", "commitment_hourly"):
        sp_by_date[str(sp["end_date"])] += float(sp["commitment_hourly"] or 0)

    all_dates = sorted(
        set(d for d, _ in ri_by_date_family.keys()) | set(sp_by_date.keys())
    )

    if not all_dates:
        return {"data": [], "layout": {"title": "No active reservations found"}}

    families = sorted(families)
    # Color palette
    palette = [
        "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#fd7e14",
        "#ffc107", "#198754", "#20c997", "#0dcaf0", "#adb5bd",
    ]

    ri_traces = []
    for i, fam in enumerate(families):
        y = [ri_by_date_family.get((d, fam), 0) for d in all_dates]
        if all(v == 0 for v in y):
            continue
        ri_traces.append({
            "type": "bar",
            "name": fam,
            "x": all_dates,
            "y": [round(v, 4) for v in y],
            "marker": {"color": palette[i % len(palette)]},
            "hovertemplate": f"<b>{fam}</b><br>Date: %{{x}}<br>$/hr: %{{y:.4f}}<extra></extra>",
        })

    sp_trace = {
        "type": "scatter",
        "mode": "lines+markers",
        "name": "Savings Plans ($/hr commitment)",
        "x": all_dates,
        "y": [round(sp_by_date.get(d, 0), 4) for d in all_dates],
        "yaxis": "y2",
        "line": {"color": "#dc3545", "width": 2, "dash": "dot"},
        "marker": {"size": 6},
        "hovertemplate": "SP commitment: $%{y:.4f}/hr<extra></extra>",
    }

    layout = {
        "barmode": "stack",
        "xaxis": {"title": "Expiration Date", "type": "category", "tickangle": -35},
        "yaxis": {"title": "RI $/hr at expiry"},
        "yaxis2": {
            "title": "SP $/hr",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
        },
        "legend": {"orientation": "h", "y": -0.35},
        "margin": {"t": 20, "b": 130, "l": 60, "r": 60},
    }

    return {"data": ri_traces + [sp_trace], "layout": layout}
