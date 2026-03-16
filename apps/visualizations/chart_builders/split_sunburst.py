def build_split_sunburst(rule_id: int, billing_period: str) -> dict:
    from apps.splitting.models import SplitResult
    from django.db.models import Sum

    rows = list(
        SplitResult.objects.filter(splitting_rule_id=rule_id, billing_period=billing_period)
        .values("tenant_tag_value", "region", "usage_type")
        .annotate(total=Sum("allocated_cost"))
    )
    if not rows:
        return {"data": [], "layout": {"title": "Cost Split"}}

    labels, parents, values = [], [], []
    rule_name = f"Rule {rule_id}"
    labels.append(rule_name)
    parents.append("")
    values.append(0)

    for r in rows:
        label = f"{r['tenant_tag_value']} / {r['usage_type']}"
        labels.append(label)
        parents.append(rule_name)
        values.append(float(r["total"]))

    return {
        "data": [{"type": "sunburst", "labels": labels, "parents": parents, "values": values}],
        "layout": {"title": f"Cost Split (Rule {rule_id}, {billing_period})"},
    }
