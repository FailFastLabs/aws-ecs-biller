from django.urls import path
from .views import CostAnomalyListView, RunAnomalyDetectionView, AnomalySummaryView, AcknowledgeAnomalyView

urlpatterns = [
    path("anomalies/runs/", RunAnomalyDetectionView.as_view()),
    path("anomalies/", CostAnomalyListView.as_view()),
    path("anomalies/summary/", AnomalySummaryView.as_view()),
    path("anomalies/<int:pk>/acknowledge/", AcknowledgeAnomalyView.as_view()),
]
