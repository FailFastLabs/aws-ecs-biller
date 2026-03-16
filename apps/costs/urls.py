from django.urls import path
from .views import (
    LineItemListView, DailyCostListView, HourlyCostListView,
    CostByServiceView, CostByRegionView, CostByAccountView,
    CostByTagView, TopNCostView,
    EdpDiscountListView, SpotPriceListView, SpotVsOdView, InstancePricingListView,
)

urlpatterns = [
    path("costs/line-items/", LineItemListView.as_view()),
    path("costs/daily/", DailyCostListView.as_view()),
    path("costs/hourly/", HourlyCostListView.as_view()),
    path("costs/by-service/", CostByServiceView.as_view()),
    path("costs/by-region/", CostByRegionView.as_view()),
    path("costs/by-account/", CostByAccountView.as_view()),
    path("costs/by-tag/", CostByTagView.as_view()),
    path("costs/top-n/", TopNCostView.as_view()),
    path("costs/edp-discounts/", EdpDiscountListView.as_view()),
    path("costs/spot-prices/", SpotPriceListView.as_view()),
    path("costs/spot-vs-od/", SpotVsOdView.as_view()),
    path("costs/instance-pricing/", InstancePricingListView.as_view()),
]
