from django.urls import path
from .views import (
    DailyTrendView, HourlyHeatmapView, ServiceBreakdownView,
    RiCoverageChartView, ForecastChartView, AnomalyChartView,
    SplitSunburstView, SpotVsOdChartView,
)

urlpatterns = [
    path("daily-trend/", DailyTrendView.as_view()),
    path("hourly-heatmap/", HourlyHeatmapView.as_view()),
    path("service-breakdown/", ServiceBreakdownView.as_view()),
    path("ri-coverage/", RiCoverageChartView.as_view()),
    path("forecast-chart/", ForecastChartView.as_view()),
    path("anomaly-chart/", AnomalyChartView.as_view()),
    path("split-sunburst/", SplitSunburstView.as_view()),
    path("spot-vs-od/", SpotVsOdChartView.as_view()),
]
