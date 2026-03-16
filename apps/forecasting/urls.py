from django.urls import path
from .views import ForecastRunListCreateView, ForecastRunDetailView, ForecastPointListView, ForecastAccuracyView

urlpatterns = [
    path("forecasting/runs/", ForecastRunListCreateView.as_view()),
    path("forecasting/runs/<int:pk>/", ForecastRunDetailView.as_view()),
    path("forecasting/runs/<int:pk>/points/", ForecastPointListView.as_view()),
    path("forecasting/runs/<int:pk>/accuracy/", ForecastAccuracyView.as_view()),
]
