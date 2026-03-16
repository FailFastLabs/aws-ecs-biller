from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ForecastRun, ForecastPoint
from .serializers import ForecastRunSerializer, ForecastPointSerializer


class ForecastRunListCreateView(generics.ListCreateAPIView):
    queryset = ForecastRun.objects.all()
    serializer_class = ForecastRunSerializer

    def create(self, request, *args, **kwargs):
        from .tasks import run_forecast_task
        account_id = request.data.get("account_id", "")
        service = request.data.get("service", "AmazonEC2")
        region = request.data.get("region", "us-east-1")
        grain = request.data.get("grain", "hourly")
        horizon = int(request.data.get("horizon", 24))
        model_name = request.data.get("model_name", "chronos-t5-small")
        task = run_forecast_task.delay(account_id, service, region, grain, horizon, model_name)
        return Response({"task_id": task.id, "status": "queued"}, status=status.HTTP_202_ACCEPTED)


class ForecastRunDetailView(generics.RetrieveAPIView):
    queryset = ForecastRun.objects.all()
    serializer_class = ForecastRunSerializer


class ForecastPointListView(generics.ListAPIView):
    serializer_class = ForecastPointSerializer

    def get_queryset(self):
        return ForecastPoint.objects.filter(forecast_run_id=self.kwargs["pk"]).order_by("timestamp")


class ForecastAccuracyView(APIView):
    def get(self, request, pk):
        from .services.chronos_forecaster import compute_accuracy
        run = ForecastRun.objects.get(pk=pk)
        return Response(compute_accuracy(run))
