from collections import defaultdict
from datetime import date, timedelta


def build_ri_expiry_timeline(account_id: str = "") -> dict:
    from apps.reservations.models import ReservedInstance, SavingsPlan

    ri_qs = ReservedInstance.objects.filter(state="active")
    sp_qs = SavingsPlan.objects.filter(state="active")
    if account_id:
        ri_qs = ri_qs.filter(account__account_id=account_id)
        sp_qs = sp_qs.filter(account__account_id=account_id)

    ri_rows = list(ri_qs.values(
        "end_date", "instance_family", "instance_type",
        "instance_count", "recurring_hourly_cost",
    ))
    sp_rows = list(sp_qs.values("end_date", "plan_type", "commitment_hourly"))

    if not ri_rows and not sp_rows:
        return {"data": [], "layout": {"title": "No active reservations found"}}

    today = date.today()

    all_ends = [r["end_date"] for r in ri_rows] + [r["end_date"] for r in sp_rows]
    last_end = max(all_ends)

    # Weekly ticks from today → last expiry
    ticks = []
    d = today
    while d <= last_end:
        ticks.append(d)
        d += timedelta(weeks=1)
    if ticks[-1] < last_end:
        ticks.append(last_end)
    tick_strs = [str(t) for t in ticks]

    families = sorted({r["instance_family"] or "other" for r in ri_rows})
    palette = [
        "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#fd7e14",
        "#ffc107", "#198754", "#20c997", "#0dcaf0", "#adb5bd",
    ]

    # ── Area traces (unchanged) ───────────────────────────────────────
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

    # ── Vertical lines + annotations at each expiry date ─────────────
    # Group what expires on each date
    expiry_labels: dict = defaultdict(list)
    for r in ri_rows:
        d_str = str(r["end_date"])
        expiry_labels[d_str].append(
            f"{r['instance_type']} ×{r['instance_count']}"
            f" (${float(r['recurring_hourly_cost'] or 0) * (r['instance_count'] or 1):.3f}/hr)"
        )
    for r in sp_rows:
        d_str = str(r["end_date"])
        expiry_labels[d_str].append(
            f"SP:{r['plan_type']} (${float(r['commitment_hourly'] or 0):.3f}/hr)"
        )

    shapes = []
    annotations = []
    for d_str, labels in sorted(expiry_labels.items()):
        shapes.append({
            "type": "line",
            "x0": d_str, "x1": d_str,
            "y0": 0, "y1": 1,
            "yref": "paper",
            "line": {"color": "rgba(100,100,100,0.4)", "width": 1, "dash": "dot"},
        })
        annotations.append({
            "x": d_str,
            "y": 0.98,
            "yref": "paper",
            "xanchor": "left",
            "yanchor": "top",
            "text": "<br>".join(labels),
            "showarrow": False,
            "textangle": -90,
            "font": {"size": 9, "color": "#555"},
            "bgcolor": "rgba(255,255,255,0.7)",
        })

    layout = {
        "xaxis": {"title": "Date", "type": "date"},
        "yaxis": {"title": "$/hr committed (active)"},
        "legend": {"orientation": "h", "y": -0.25},
        "margin": {"t": 20, "b": 80, "l": 60, "r": 20},
        "hovermode": "x unified",
        "shapes": shapes,
        "annotations": annotations,
    }

    return {"data": ri_traces + [sp_trace], "layout": layout}
