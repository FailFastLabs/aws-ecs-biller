from django.urls import path
from .views import SplittingRuleListCreateView, SplittingRuleDetailView, RunSplitView, SplitResultListView, VerifySplitView

urlpatterns = [
    path("splitting/rules/", SplittingRuleListCreateView.as_view()),
    path("splitting/rules/<int:pk>/", SplittingRuleDetailView.as_view()),
    path("splitting/rules/<int:pk>/run/", RunSplitView.as_view()),
    path("splitting/results/", SplitResultListView.as_view()),
    path("splitting/results/verify/", VerifySplitView.as_view()),
]
