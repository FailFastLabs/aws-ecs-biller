from celery import shared_task


@shared_task
def run_anomaly_detection_task():
    from apps.costs.models import HourlyCostAggregate
    from .services.ensemble import run_ensemble_detection

    combos = HourlyCostAggregate.objects.values("linked_account_id", "service", "region").distinct()
    for combo in combos:
        run_ensemble_detection(
            account_id=combo["linked_account_id"],
            service=combo["service"],
            region=combo["region"],
            grain="hourly",
        )
