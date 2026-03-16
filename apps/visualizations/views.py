from rest_framework.response import Response
from rest_framework.views import APIView


class DailyTrendView(APIView):
    def get(self, request):
        from .chart_builders.daily_trend import build_daily_trend
        params = {
            "account_id": request.query_params.get("account_id"),
            "service": request.query_params.get("service"),
            "region": request.query_params.get("region"),
            "start_date": request.query_params.get("start_date"),
            "end_date": request.query_params.get("end_date"),
        }
        return Response(build_daily_trend(**params))


class HourlyHeatmapView(APIView):
    def get(self, request):
        from .chart_builders.hourly_heatmap import build_hourly_heatmap
        return Response(build_hourly_heatmap(
            account_id=request.query_params.get("account_id"),
            service=request.query_params.get("service"),
            region=request.query_params.get("region"),
        ))


class ServiceBreakdownView(APIView):
    def get(self, request):
        from .chart_builders.service_breakdown import build_service_breakdown
        return Response(build_service_breakdown(
            billing_period=request.query_params.get("billing_period", "2025-01"),
            account_id=request.query_params.get("account_id"),
        ))


class RiCoverageChartView(APIView):
    def get(self, request):
        from .chart_builders.ri_coverage import build_ri_coverage
        return Response(build_ri_coverage(
            account_id=request.query_params.get("account_id", ""),
            billing_period=request.query_params.get("billing_period", "2025-01"),
        ))


class ForecastChartView(APIView):
    def get(self, request):
        from .chart_builders.forecast_chart import build_forecast_chart
        run_id = int(request.query_params.get("forecast_run_id", 0))
        return Response(build_forecast_chart(run_id))


class AnomalyChartView(APIView):
    def get(self, request):
        from .chart_builders.anomaly_chart import build_anomaly_chart
        return Response(build_anomaly_chart(
            account_id=request.query_params.get("account_id", ""),
            service=request.query_params.get("service", "AmazonEC2"),
            region=request.query_params.get("region", "us-east-1"),
            start=request.query_params.get("start", "2025-01-01"),
            end=request.query_params.get("end", "2025-02-01"),
        ))


class SplitSunburstView(APIView):
    def get(self, request):
        from .chart_builders.split_sunburst import build_split_sunburst
        return Response(build_split_sunburst(
            rule_id=int(request.query_params.get("rule_id", 0)),
            billing_period=request.query_params.get("billing_period", "2025-01"),
        ))


class SpotVsOdChartView(APIView):
    def get(self, request):
        from .chart_builders.spot_prices import build_spot_vs_od_chart
        return Response(build_spot_vs_od_chart(
            region=request.query_params.get("region", "us-east-1"),
            instance_type=request.query_params.get("instance_type", "m5.large"),
        ))


class RiUsageBreakdownView(APIView):
    def get(self, request):
        from .chart_builders.ri_usage_breakdown import build_ri_usage_breakdown
        return Response(build_ri_usage_breakdown(
            account_id=request.query_params.get("account_id", ""),
            billing_period=request.query_params.get("billing_period", ""),
            instance_type=request.query_params.get("instance_type", ""),
            region=request.query_params.get("region", ""),
            limit=int(request.query_params.get("limit", 100)),
        ))


class RiCounterfactualView(APIView):
    def get(self, request):
        from .chart_builders.ri_counterfactual import build_ri_counterfactual
        return Response(build_ri_counterfactual(
            account_id=request.query_params.get("account_id", ""),
            instance_type=request.query_params.get("instance_type", ""),
            region=request.query_params.get("region", ""),
            reserved_count=float(request.query_params.get("reserved_count", 0)),
            days=int(request.query_params.get("days", 7)),
        ))


class RiExpiryTimelineView(APIView):
    def get(self, request):
        from .chart_builders.ri_expiry_timeline import build_ri_expiry_timeline
        return Response(build_ri_expiry_timeline(
            account_id=request.query_params.get("account_id", ""),
        ))
