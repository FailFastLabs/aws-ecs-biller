from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("costs/", views.costs, name="costs"),
    path("reservations/", views.reservations, name="reservations"),
    path("anomalies/", views.anomalies, name="anomalies"),
    path("forecasting/", views.forecasting, name="forecasting"),
    path("splitting/", views.splitting, name="splitting"),
]
