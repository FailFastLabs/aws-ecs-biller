from django.db.models import Sum
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import LineItemFilter, DailyAggregateFilter, HourlyAggregateFilter
from .models import (LineItem, DailyCostAggregate, HourlyCostAggregate,
                     EdpDiscount, SpotPriceHistory, InstancePricing)
from .serializers import (LineItemSerializer, DailyCostAggregateSerializer,
                           HourlyCostAggregateSerializer, EdpDiscountSerializer,
                           SpotPriceHistorySerializer, InstancePricingSerializer)


class LineItemListView(generics.ListAPIView):
    queryset = LineItem.objects.all()
    serializer_class = LineItemSerializer
    filterset_class = LineItemFilter


class DailyCostListView(generics.ListAPIView):
    queryset = DailyCostAggregate.objects.all().order_by("date")
    serializer_class = DailyCostAggregateSerializer
    filterset_class = DailyAggregateFilter


class HourlyCostListView(generics.ListAPIView):
    queryset = HourlyCostAggregate.objects.all().order_by("hour")
    serializer_class = HourlyCostAggregateSerializer
    filterset_class = HourlyAggregateFilter


class CostByServiceView(APIView):
    def get(self, request):
        bp = request.query_params.get("billing_period", "")
        qs = LineItem.objects.all()
        if bp:
            qs = qs.filter(billing_period=bp)
        data = list(
            qs.values("service")
            .annotate(total=Sum("unblended_cost"))
            .order_by("-total")
        )
        return Response({"results": data})


class CostByRegionView(APIView):
    def get(self, request):
        bp = request.query_params.get("billing_period", "")
        qs = LineItem.objects.all()
        if bp:
            qs = qs.filter(billing_period=bp)
        data = list(
            qs.values("region")
            .annotate(total=Sum("unblended_cost"))
            .order_by("-total")
        )
        return Response({"results": data})


class CostByAccountView(APIView):
    def get(self, request):
        bp = request.query_params.get("billing_period", "")
        qs = LineItem.objects.all()
        if bp:
            qs = qs.filter(billing_period=bp)
        data = list(
            qs.values("linked_account_id", "linked_account_name")
            .annotate(total=Sum("unblended_cost"))
            .order_by("-total")
        )
        return Response({"results": data})


class CostByTagView(APIView):
    def get(self, request):
        tag_key = request.query_params.get("tag_key", "")
        bp = request.query_params.get("billing_period", "")
        qs = LineItem.objects.filter(tags__has_key=tag_key)
        if bp:
            qs = qs.filter(billing_period=bp)
        # Group by tag value
        from django.db.models import F
        from django.db.models.expressions import RawSQL
        rows = qs.values("tags").annotate(total=Sum("unblended_cost"))
        result = {}
        for row in rows:
            val = row["tags"].get(tag_key, "")
            result[val] = result.get(val, 0) + float(row["total"] or 0)
        data = [{"tag_value": k, "total": v} for k, v in sorted(result.items(), key=lambda x: -x[1])]
        return Response({"results": data})


class TopNCostView(APIView):
    def get(self, request):
        n = int(request.query_params.get("n", 10))
        group_by = request.query_params.get("group_by", "service")
        bp = request.query_params.get("billing_period", "")
        allowed = {"service", "region", "linked_account_id", "usage_type", "instance_type",
                   "line_item_type", "operation"}
        if group_by not in allowed:
            return Response({"error": f"group_by must be one of {allowed}"}, status=status.HTTP_400_BAD_REQUEST)
        qs = LineItem.objects.all()
        if bp:
            qs = qs.filter(billing_period=bp)
        data = list(
            qs.values(group_by)
            .annotate(total=Sum("unblended_cost"))
            .order_by("-total")[:n]
        )
        return Response({"results": data})


class EdpDiscountListView(generics.ListAPIView):
    queryset = EdpDiscount.objects.all()
    serializer_class = EdpDiscountSerializer


class SpotPriceListView(generics.ListAPIView):
    queryset = SpotPriceHistory.objects.all().order_by("timestamp")
    serializer_class = SpotPriceHistorySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        region = self.request.query_params.get("region")
        itype = self.request.query_params.get("instance_type")
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if region:
            qs = qs.filter(region=region)
        if itype:
            qs = qs.filter(instance_type=itype)
        if start:
            qs = qs.filter(timestamp__gte=start)
        if end:
            qs = qs.filter(timestamp__lte=end)
        return qs


class SpotVsOdView(APIView):
    def get(self, request):
        region = request.query_params.get("region", "us-east-1")
        itype = request.query_params.get("instance_type", "m5.large")
        try:
            pricing = InstancePricing.objects.filter(
                region=region, instance_type=itype
            ).latest("effective_date")
            od = float(pricing.od_hourly)
        except InstancePricing.DoesNotExist:
            od = None

        spots = SpotPriceHistory.objects.filter(region=region, instance_type=itype)
        if not spots.exists():
            return Response({"od_hourly": od, "avg_spot": None, "max_spot": None, "pct_savings": None})

        agg = spots.aggregate(avg=Sum("spot_price") / spots.count() if spots.count() else None)
        prices = [float(s) for s in spots.values_list("spot_price", flat=True)]
        avg_spot = sum(prices) / len(prices)
        max_spot = max(prices)
        pct_savings = ((od - avg_spot) / od * 100) if od else None
        return Response({
            "od_hourly": od,
            "avg_spot": round(avg_spot, 6),
            "max_spot": round(max_spot, 6),
            "pct_savings": round(pct_savings, 2) if pct_savings else None,
        })


class InstancePricingListView(generics.ListAPIView):
    queryset = InstancePricing.objects.all()
    serializer_class = InstancePricingSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        region = self.request.query_params.get("region")
        itype = self.request.query_params.get("instance_type")
        if region:
            qs = qs.filter(region=region)
        if itype:
            qs = qs.filter(instance_type=itype)
        return qs
