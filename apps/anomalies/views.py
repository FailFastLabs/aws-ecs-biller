from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import CostAnomaly
from .serializers import CostAnomalySerializer
import django_filters


class CostAnomalyFilter(django_filters.FilterSet):
    class Meta:
        model = CostAnomaly
        fields = ["service", "direction", "acknowledged", "linked_account_id"]


class CostAnomalyListView(generics.ListAPIView):
    queryset = CostAnomaly.objects.all().order_by("-period_start")
    serializer_class = CostAnomalySerializer
    filterset_class = CostAnomalyFilter


class RunAnomalyDetectionView(APIView):
    def post(self, request):
        from .services.ensemble import run_ensemble_detection
        account_id = request.data.get("account_id", "")
        service = request.data.get("service", "AmazonEC2")
        region = request.data.get("region", "us-east-1")
        grain = request.data.get("grain", "hourly")
        sigma = float(request.data.get("sigma_threshold", 3.5))
        min_delta = float(request.data.get("min_cost_delta", 5.0))
        anomalies = run_ensemble_detection(account_id, service, region, grain,
                                            sigma_threshold=sigma, min_cost_delta=min_delta)
        return Response({"detected": len(anomalies)}, status=status.HTTP_201_CREATED)


class AnomalySummaryView(APIView):
    def get(self, request):
        from django.db.models import Count
        spikes = CostAnomaly.objects.filter(direction="spike").count()
        drops = CostAnomaly.objects.filter(direction="drop").count()
        top = list(
            CostAnomaly.objects.values("service")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        return Response({"spike_count": spikes, "drop_count": drops, "top_services": top})


class AcknowledgeAnomalyView(APIView):
    def patch(self, request, pk):
        anomaly = CostAnomaly.objects.get(pk=pk)
        anomaly.acknowledged = True
        anomaly.notes = request.data.get("notes", "")
        anomaly.save(update_fields=["acknowledged", "notes"])
        return Response(CostAnomalySerializer(anomaly).data)
