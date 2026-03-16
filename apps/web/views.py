from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count, Max


def _current_billing_period():
    now = timezone.now()
    return f"{now.year}-{now.month:02d}"


def _billing_periods(n=12):
    """Return last n billing periods as strings."""
    from datetime import date
    import calendar
    today = date.today()
    periods = []
    year, month = today.year, today.month
    for _ in range(n):
        periods.append(f"{year}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return periods


def dashboard(request):
    from apps.accounts.models import AwsAccount
    from apps.costs.models import DailyCostAggregate, LineItem
    from apps.anomalies.models import CostAnomaly

    bp = request.GET.get("billing_period", _current_billing_period())
    accounts = list(AwsAccount.objects.values("account_id", "account_name"))

    # Summary cards
    month_total = DailyCostAggregate.objects.filter(
        date__startswith=bp[:7]
    ).aggregate(total=Sum("unblended_cost"))["total"] or 0

    top_services = list(
        DailyCostAggregate.objects.filter(date__startswith=bp[:7])
        .values("service")
        .annotate(total=Sum("unblended_cost"))
        .order_by("-total")[:5]
    )

    anomaly_count = CostAnomaly.objects.filter(acknowledged=False).count()

    line_item_count = LineItem.objects.filter(billing_period=bp).count()

    return render(request, "web/dashboard.html", {
        "accounts": accounts,
        "billing_periods": _billing_periods(),
        "billing_period": bp,
        "month_total": round(float(month_total), 2),
        "top_services": top_services,
        "anomaly_count": anomaly_count,
        "line_item_count": line_item_count,
    })


def costs(request):
    from apps.accounts.models import AwsAccount
    from apps.costs.models import LineItem

    bp = request.GET.get("billing_period", _current_billing_period())
    account_id = request.GET.get("account_id", "")
    service = request.GET.get("service", "")
    region = request.GET.get("region", "")

    accounts = list(AwsAccount.objects.values("account_id", "account_name"))
    services = list(
        LineItem.objects.values_list("service", flat=True)
        .distinct().order_by("service")
    )
    regions = list(
        LineItem.objects.values_list("region", flat=True)
        .distinct().order_by("region")
    )

    return render(request, "web/costs.html", {
        "accounts": accounts,
        "billing_periods": _billing_periods(),
        "billing_period": bp,
        "account_id": account_id,
        "services": services,
        "regions": regions,
        "service": service,
        "region": region,
    })


def reservations(request):
    from apps.accounts.models import AwsAccount
    from apps.reservations.models import ReservedInstance, SavingsPlan

    bp = request.GET.get("billing_period", _current_billing_period())
    account_id = request.GET.get("account_id", "")
    accounts = list(AwsAccount.objects.values("account_id", "account_name"))

    ri_summary = list(
        ReservedInstance.objects.filter(state="active")
        .values("instance_type", "region", "offering_class")
        .annotate(count=Count("id"), units=Sum("normalized_units"))
        .order_by("-units")[:20]
    )

    sp_summary = list(
        SavingsPlan.objects.filter(state="active")
        .values("plan_type")
        .annotate(count=Count("id"), commitment=Sum("commitment_hourly"))
        .order_by("-commitment")[:10]
    )

    return render(request, "web/reservations.html", {
        "accounts": accounts,
        "billing_periods": _billing_periods(),
        "billing_period": bp,
        "account_id": account_id,
        "ri_summary": ri_summary,
        "sp_summary": sp_summary,
    })


def anomalies(request):
    from apps.accounts.models import AwsAccount
    from apps.anomalies.models import CostAnomaly

    account_id = request.GET.get("account_id", "")
    service = request.GET.get("service", "")
    region = request.GET.get("region", "us-east-1")
    start = request.GET.get("start", "")
    end = request.GET.get("end", "")
    acknowledged = request.GET.get("acknowledged", "")

    accounts = list(AwsAccount.objects.values("account_id", "account_name"))

    qs = CostAnomaly.objects.select_related("detection_run").order_by("-period_start")
    if account_id:
        qs = qs.filter(linked_account_id=account_id)
    if service:
        qs = qs.filter(service=service)
    if acknowledged == "false":
        qs = qs.filter(acknowledged=False)
    elif acknowledged == "true":
        qs = qs.filter(acknowledged=True)

    anomaly_list = list(qs[:50].values(
        "id", "service", "region", "linked_account_id",
        "period_start", "direction", "observed_cost", "baseline_cost",
        "pct_change", "z_score", "acknowledged",
    ))

    services = list(
        CostAnomaly.objects.values_list("service", flat=True).distinct().order_by("service")
    )

    return render(request, "web/anomalies.html", {
        "accounts": accounts,
        "anomaly_list": anomaly_list,
        "services": services,
        "account_id": account_id,
        "service": service,
        "region": region,
        "start": start,
        "end": end,
        "acknowledged": acknowledged,
    })


def forecasting(request):
    from apps.accounts.models import AwsAccount
    from apps.forecasting.models import ForecastRun

    account_id = request.GET.get("account_id", "")
    run_id = request.GET.get("run_id", "")

    accounts = list(AwsAccount.objects.values("account_id", "account_name"))
    runs = list(
        ForecastRun.objects.select_related("account")
        .order_by("-created_at")[:20]
        .values("id", "grain", "service", "region", "training_end",
                "forecast_horizon", "model_name", "mae", "mape",
                "account__account_name", "created_at")
    )

    selected_run = None
    if run_id:
        try:
            selected_run = ForecastRun.objects.get(id=run_id)
        except ForecastRun.DoesNotExist:
            pass
    elif runs:
        run_id = runs[0]["id"]

    return render(request, "web/forecasting.html", {
        "accounts": accounts,
        "runs": runs,
        "run_id": run_id,
        "selected_run": selected_run,
        "account_id": account_id,
    })


def splitting(request):
    from apps.splitting.models import SplittingRule, SplitResult
    from django.db.models import Sum

    rule_id = request.GET.get("rule_id", "")
    bp = request.GET.get("billing_period", _current_billing_period())

    rules = list(SplittingRule.objects.values(
        "id", "name", "service", "region", "weight_strategy", "active"
    ).order_by("name"))

    selected_rule = None
    tenant_breakdown = []
    if rule_id:
        try:
            selected_rule = SplittingRule.objects.get(id=rule_id)
            tenant_breakdown = list(
                SplitResult.objects.filter(splitting_rule=selected_rule, billing_period=bp)
                .values("tenant_tag_value")
                .annotate(total=Sum("allocated_cost"))
                .order_by("-total")
            )
        except SplittingRule.DoesNotExist:
            pass
    elif rules:
        rule_id = rules[0]["id"]

    return render(request, "web/splitting.html", {
        "rules": rules,
        "rule_id": rule_id,
        "selected_rule": selected_rule,
        "billing_periods": _billing_periods(),
        "billing_period": bp,
        "tenant_breakdown": tenant_breakdown,
    })
