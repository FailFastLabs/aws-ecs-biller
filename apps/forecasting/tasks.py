from celery import shared_task
from django.utils import timezone
from datetime import timedelta


@shared_task
def run_forecast_task(account_id, service, region, grain="hourly",
                       horizon=24, model_name="chronos-t5-small"):
    from .services.chronos_forecaster import run_chronos_forecast
    from datetime import date
    training_end = date.today() - timedelta(days=1)
    training_start = training_end - timedelta(days=60)
    run = run_chronos_forecast(account_id, service, region, grain,
                                training_start, training_end, horizon, model_name)
    return run.id


@shared_task
def backfill_actuals_task():
    from .services.chronos_forecaster import backfill_actuals, compute_accuracy
    from .models import ForecastRun
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=30)
    for run in ForecastRun.objects.filter(created_at__gte=cutoff):
        backfill_actuals(run)
        compute_accuracy(run)
