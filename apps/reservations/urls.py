from django.urls import path
from .views import (
    ReservedInstanceListView, SavingsPlanListView,
    RiCoverageView, RiUtilizationView, SpCounterfactualView,
    RiRecommendationListView, RunRecommendationsView, ConvertibleSwapsView,
    PortfolioRecommendationView,
)

urlpatterns = [
    path("reservations/ris/", ReservedInstanceListView.as_view()),
    path("reservations/savings-plans/", SavingsPlanListView.as_view()),
    path("reservations/coverage/", RiCoverageView.as_view()),
    path("reservations/utilization/", RiUtilizationView.as_view()),
    path("reservations/sp-counterfactual/", SpCounterfactualView.as_view()),
    path("reservations/recommendations/", RiRecommendationListView.as_view()),
    path("reservations/recommendations/run/", RunRecommendationsView.as_view()),
    path("reservations/convertible-swaps/", ConvertibleSwapsView.as_view()),
    path("reservations/portfolio-recommendation/", PortfolioRecommendationView.as_view()),
]
