from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncHour


def refresh_daily_aggregates(billing_period: str) -> None:
    from apps.costs.models import LineItem, DailyCostAggregate
    qs = (
        LineItem.objects.filter(billing_period=billing_period)
        .annotate(date=TruncDate("usage_start"))
        .values("date", "linked_account_id", "service", "region", "usage_type", "line_item_type")
        .annotate(
            total_unblended=Sum("unblended_cost"),
            total_usage=Sum("usage_quantity"),
        )
    )
    for row in qs:
        if row["date"] is None:
            continue
        DailyCostAggregate.objects.update_or_create(
            date=row["date"],
            linked_account_id=row["linked_account_id"] or "",
            service=row["service"] or "",
            region=row["region"] or "",
            usage_type=row["usage_type"] or "",
            line_item_type=row["line_item_type"] or "",
            defaults={
                "unblended_cost": row["total_unblended"] or 0,
                "usage_quantity": row["total_usage"] or 0,
            },
        )


def refresh_hourly_aggregates(billing_period: str) -> None:
    from apps.costs.models import LineItem, HourlyCostAggregate
    qs = (
        LineItem.objects.filter(billing_period=billing_period)
        .annotate(hour=TruncHour("usage_start"))
        .values("hour", "linked_account_id", "service", "region", "usage_type", "line_item_type")
        .annotate(
            total_unblended=Sum("unblended_cost"),
            total_usage=Sum("usage_quantity"),
        )
    )
    for row in qs:
        if row["hour"] is None:
            continue
        HourlyCostAggregate.objects.update_or_create(
            hour=row["hour"],
            linked_account_id=row["linked_account_id"] or "",
            service=row["service"] or "",
            region=row["region"] or "",
            usage_type=row["usage_type"] or "",
            line_item_type=row["line_item_type"] or "",
            defaults={
                "unblended_cost": row["total_unblended"] or 0,
                "usage_quantity": row["total_usage"] or 0,
            },
        )
