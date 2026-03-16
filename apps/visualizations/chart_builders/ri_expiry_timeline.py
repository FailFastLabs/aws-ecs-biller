from datetime import date, timedelta


def build_ri_expiry_timeline(account_id: str = "") -> dict:
    from apps.reservations.models import ReservedInstance, SavingsPlan

    ri_qs = ReservedInstance.objects.filter(state="active")
    sp_qs = SavingsPlan.objects.filter(state="active")
    if account_id:
        ri_qs = ri_qs.filter(account__account_id=account_id)
        sp_qs = sp_qs.filter(account__account_id=account_id)

    ri_rows = list(ri_qs.values("end_date", "instance_family", "recurring_hourly_cost", "instance_count"))
    sp_rows = list(sp_qs.values("end_date", "commitment_hourly"))

    if not ri_rows and not sp_rows:
        return {"data": [], "layout": {"title": "No active reservations found"}}

    today = date.today()

    # Find date range: today → last expiry date, sampled weekly
    all_ends = [r["end_date"] for r in ri_rows] + [r["end_date"] for r in sp_rows]
    last_end = max(all_ends)
    # Weekly date ticks from today to last_end
    ticks = []
    d = today
    while d <= last_end:
        ticks.append(d)
        d += timedelta(weeks=1)
    if ticks[-1] < last_end:
        ticks.append(last_end)

    tick_strs = [str(t) for t in ticks]

    # For each tick: sum $/hr of RIs still active per family (end_date >= tick)
    families = sorted({r["instance_family"] or "other" for r in ri_rows})
    palette = [
        "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#fd7e14",
        "#ffc107", "#198754", "#20c997", "#0dcaf0", "#adb5bd",
    ]

    ri_traces = []
    for i, fam in enumerate(families):
        fam_rows = [r for r in ri_rows if (r["instance_family"] or "other") == fam]
        y = []
        for tick in ticks:
            total = sum(
                float(r["recurring_hourly_cost"] or 0) * (r["instance_count"] or 1)
                for r in fam_rows
                if r["end_date"] >= tick
            )
            y.append(round(total, 4))

        if all(v == 0 for v in y):
            continue

        color_hex = palette[i % len(palette)]
        ri_traces.append({
            "type": "scatter",
            "mode": "lines",
            "name": fam,
            "x": tick_strs,
            "y": y,
            "stackgroup": "ri",
            "line": {"shape": "hv", "color": color_hex, "width": 0.5},
            "fillcolor": color_hex + "99",
            "hovertemplate": f"<b>{fam}</b><br>%{{x}}<br>$/hr: %{{y:.4f}}<extra></extra>",
        })

    # SP Heaviside: for each tick sum commitment of SPs still active
    sp_y = []
    for tick in ticks:
        total = sum(
            float(r["commitment_hourly"] or 0)
            for r in sp_rows
            if r["end_date"] >= tick
        )
        sp_y.append(round(total, 4))

    sp_trace = {
        "type": "scatter",
        "mode": "lines",
        "name": "Savings Plans ($/hr)",
        "x": tick_strs,
        "y": sp_y,
        "stackgroup": "sp",
        "line": {"shape": "hv", "color": "#dc3545", "width": 2, "dash": "dot"},
        "fillcolor": "rgba(220,53,69,0.20)",
        "hovertemplate": "SP: $%{y:.4f}/hr<extra></extra>",
    }

    layout = {
        "xaxis": {"title": "Date", "type": "date"},
        "yaxis": {"title": "$/hr committed (active)"},
        "legend": {"orientation": "h", "y": -0.25},
        "margin": {"t": 20, "b": 80, "l": 60, "r": 20},
        "hovermode": "x unified",
    }

    return {"data": ri_traces + [sp_trace], "layout": layout}
