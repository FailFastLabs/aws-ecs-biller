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
        from apps.reservations.models import ReservedInstance
        account_id = request.data.get("account_id", "")
        billing_period = request.data.get("billing_period", "")

        swaps = optimize_convertible_ris(account_id, billing_period)

        # Current total RI hourly cost
        ri_qs = ReservedInstance.objects.filter(state="active")
        if account_id:
            ri_qs = ri_qs.filter(account__account_id=account_id)
        current_hourly = sum(
            float(r["recurring_hourly_cost"]) * r["instance_count"]
            for r in ri_qs.values("recurring_hourly_cost", "instance_count")
        )
        # Projected after swaps (subtract monthly savings converted to hourly)
        total_monthly_savings = sum(s["monthly_savings"] for s in swaps)
        projected_hourly = current_hourly - (total_monthly_savings / 720)

        return Response({
            "swaps": swaps,
            "count": len(swaps),
            "current_hourly": round(current_hourly, 4),
            "projected_hourly": round(projected_hourly, 4),
            "hourly_savings": round(current_hourly - projected_hourly, 4),
            "monthly_savings_total": round(total_monthly_savings, 2),
        })


class PortfolioRecommendationView(APIView):
    def get(self, request):
        from .services.portfolio_recommendation import compute_portfolio_recommendation
        return Response(compute_portfolio_recommendation(
            account_id=request.query_params.get("account_id", ""),
            billing_period=request.query_params.get("billing_period", ""),
            n_days=int(request.query_params.get("n_days", 30)),
        ))


class ConvertibleSwapsView(APIView):
    def get(self, request):
        from .services.convertible_optimizer import optimize_convertible_ris
        account_id = request.query_params.get("account_id", "")
        billing_period = request.query_params.get("billing_period", "")
        swaps = optimize_convertible_ris(account_id, billing_period)
        return Response({"swaps": swaps})
