from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ReservedInstance, SavingsPlan, RiRecommendation
from .serializers import ReservedInstanceSerializer, SavingsPlanSerializer, RiRecommendationSerializer


class ReservedInstanceListView(generics.ListAPIView):
    queryset = ReservedInstance.objects.all()
    serializer_class = ReservedInstanceSerializer


class SavingsPlanListView(generics.ListAPIView):
    queryset = SavingsPlan.objects.all()
    serializer_class = SavingsPlanSerializer


class RiCoverageView(APIView):
    def get(self, request):
        from .services.coverage import compute_ri_coverage
        account_id = request.query_params.get("account_id", "")
        billing_period = request.query_params.get("billing_period", "")
        df = compute_ri_coverage(account_id, billing_period)
        return Response({"results": df.to_dict("records")})


class RiUtilizationView(APIView):
    def get(self, request):
        from .services.utilization import compute_ri_utilization
        account_id = request.query_params.get("account_id", "")
        billing_period = request.query_params.get("billing_period", "")
        df = compute_ri_utilization(account_id, billing_period)
        return Response({"results": df.to_dict("records") if not df.empty else []})


class SpCounterfactualView(APIView):
    def get(self, request):
        from .services.sp_counterfactual import compute_sp_counterfactual
        account_id = request.query_params.get("account_id", "")
        billing_period = request.query_params.get("billing_period", "")
        result = compute_sp_counterfactual(account_id, billing_period)
        return Response(result)


class RiRecommendationListView(generics.ListAPIView):
    queryset = RiRecommendation.objects.all()
    serializer_class = RiRecommendationSerializer


class RunRecommendationsView(APIView):
    def post(self, request):
        from .services.convertible_optimizer import optimize_convertible_ris
        account_id = request.data.get("account_id", "")
        billing_period = request.data.get("billing_period", "")
        swaps = optimize_convertible_ris(account_id, billing_period)
        return Response({"swaps": swaps, "count": len(swaps)})


class ConvertibleSwapsView(APIView):
    def get(self, request):
        from .services.convertible_optimizer import optimize_convertible_ris
        account_id = request.query_params.get("account_id", "")
        billing_period = request.query_params.get("billing_period", "")
        swaps = optimize_convertible_ris(account_id, billing_period)
        return Response({"swaps": swaps})
