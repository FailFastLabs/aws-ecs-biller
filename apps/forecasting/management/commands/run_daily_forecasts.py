"""run_daily_forecasts — discover all grouping combinations and run forecasts.

Grouping levels:
  L1  region
  L2  region + service
  L3  region + service + instance_type

Grains:
  daily  — 7-day horizon (default)
  hourly — 48-hour horizon (default)
  both   — runs both (default)

Skips any combination already forecast today for that grain.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run daily and/or hourly forecasts for all region / service / instance_type groupings"

    def add_arguments(self, parser):
        parser.add_argument(
            "--account-id", default=None,
            help="Limit to a single AWS account ID (default: all payer accounts)",
        )
        parser.add_argument(
            "--horizon", type=int, default=7,
            help="Daily forecast horizon in days (default: 7)",
        )
        parser.add_argument(
            "--hourly-horizon", type=int, default=48,
            help="Hourly forecast horizon in hours (default: 48)",
        )
        parser.add_argument(
            "--lookback-days", type=int, default=90,
            help="Training window in days (default: 90)",
        )
        parser.add_argument(
            "--min-daily-cost", type=float, default=1.0,
            help="Skip combinations whose average daily cost < this (default: $1)",
        )
        parser.add_argument(
            "--grain", choices=["daily", "hourly", "both"], default="both",
            help="Which forecast grain(s) to run (default: both)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print combinations without running forecasts",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import AwsAccount
        from apps.costs.models import DailyCostAggregate, LineItem
        from apps.forecasting.services.chronos_forecaster import run_chronos_forecast

        training_end   = date.today() - timedelta(days=1)
        training_start = training_end - timedelta(days=options["lookback_days"])
        horizon        = options["horizon"]
        hourly_horizon = options["hourly_horizon"]
        min_cost       = options["min_daily_cost"]
        dry_run        = options["dry_run"]
        run_daily      = options["grain"] in ("daily",  "both")
        run_hourly     = options["grain"] in ("hourly", "both")

        if options["account_id"]:
            accounts = list(AwsAccount.objects.filter(account_id=options["account_id"]))
        else:
            accounts = list(AwsAccount.objects.filter(is_payer=True))

        if not accounts:
            self.stderr.write("No matching accounts found.")
            return

        today = date.today()
        ran = skipped = errors = 0

        def _run(aid, region, service, itype, grain, h):
            nonlocal ran, skipped, errors
            label_grain = "D" if grain == "daily" else "H"
            label = f"[{label_grain}] {region}" + (f"/{service}" if service else "") + (f"/{itype}" if itype else "")

            if _already_run_today(aid, region, service, itype, grain, today):
                skipped += 1
                return
            if dry_run:
                self.stdout.write(f"    DRY {label}")
                return
            try:
                result = run_chronos_forecast(
                    aid, region, grain, training_start, training_end,
                    h, service=service, instance_type=itype,
                )
                ran += 1
                self.stdout.write(f"    OK  {label} run_id={result.id}")
            except Exception as exc:
                errors += 1
                self.stderr.write(f"    ERR {label}: {exc}")

        for account in accounts:
            aid = account.account_id
            self.stdout.write(f"\nAccount {aid} ({account.account_name})")

            # ── L1: distinct regions ─────────────────────────────────────────
            regions = list(
                DailyCostAggregate.objects
                .filter(linked_account_id=aid, date__range=(training_start, training_end))
                .values_list("region", flat=True)
                .distinct()
            )
            self.stdout.write(f"  L1 regions: {len(regions)}")
            for region in regions:
                avg = _avg_daily_cost_region(aid, region, training_start, training_end)
                if avg < min_cost:
                    skipped += (1 if run_daily else 0) + (1 if run_hourly else 0)
                    continue
                if run_daily:
                    _run(aid, region, "", "", "daily",  horizon)
                if run_hourly:
                    _run(aid, region, "", "", "hourly", hourly_horizon)

            # ── L2: distinct (region, service) pairs ─────────────────────────
            l2_pairs = list(
                DailyCostAggregate.objects
                .filter(linked_account_id=aid, date__range=(training_start, training_end))
                .values_list("region", "service")
                .distinct()
            )
            self.stdout.write(f"  L2 region+service pairs: {len(l2_pairs)}")
            for region, service in l2_pairs:
                avg = _avg_daily_cost_service(aid, region, service, training_start, training_end)
                if avg < min_cost:
                    skipped += (1 if run_daily else 0) + (1 if run_hourly else 0)
                    continue
                if run_daily:
                    _run(aid, region, service, "", "daily",  horizon)
                if run_hourly:
                    _run(aid, region, service, "", "hourly", hourly_horizon)

            # ── L3: distinct (region, service, instance_type) triples ────────
            l3_triples = list(
                LineItem.objects
                .filter(
                    linked_account_id=aid,
                    usage_start__date__range=(training_start, training_end),
                )
                .exclude(instance_type="")
                .values_list("region", "service", "instance_type")
                .distinct()
            )
            self.stdout.write(f"  L3 region+service+itype triples: {len(l3_triples)}")
            for region, service, itype in l3_triples:
                avg = _avg_daily_cost_instance(aid, region, service, itype, training_start, training_end)
                if avg < min_cost:
                    skipped += (1 if run_daily else 0) + (1 if run_hourly else 0)
                    continue
                if run_daily:
                    _run(aid, region, service, itype, "daily",  horizon)
                if run_hourly:
                    _run(aid, region, service, itype, "hourly", hourly_horizon)

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete — no forecasts created."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. ran={ran}  skipped={skipped}  errors={errors}")
            )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _already_run_today(account_id, region, service, instance_type, grain, today):
    from apps.forecasting.models import ForecastRun
    return ForecastRun.objects.filter(
        account__account_id=account_id,
        region=region, service=service, instance_type=instance_type,
        grain=grain,
        created_at__date=today,
    ).exists()


def _avg_daily_cost_region(account_id, region, start, end):
    from django.db.models import Sum
    from apps.costs.models import DailyCostAggregate
    agg = (DailyCostAggregate.objects
           .filter(linked_account_id=account_id, region=region, date__range=(start, end))
           .values("date").annotate(c=Sum("unblended_cost")))
    costs = [float(r["c"]) for r in agg]
    return sum(costs) / len(costs) if costs else 0.0


def _avg_daily_cost_service(account_id, region, service, start, end):
    from django.db.models import Sum
    from apps.costs.models import DailyCostAggregate
    agg = (DailyCostAggregate.objects
           .filter(linked_account_id=account_id, region=region, service=service,
                   date__range=(start, end))
           .values("date").annotate(c=Sum("unblended_cost")))
    costs = [float(r["c"]) for r in agg]
    return sum(costs) / len(costs) if costs else 0.0


def _avg_daily_cost_instance(account_id, region, service, instance_type, start, end):
    from django.db.models import Sum
    from django.db.models.functions import TruncDate
    from apps.costs.models import LineItem
    agg = (LineItem.objects
           .filter(linked_account_id=account_id, region=region, service=service,
                   instance_type=instance_type, usage_start__date__range=(start, end))
           .annotate(day=TruncDate("usage_start"))
           .values("day").annotate(c=Sum("unblended_cost")))
    costs = [float(r["c"]) for r in agg]
    return sum(costs) / len(costs) if costs else 0.0
