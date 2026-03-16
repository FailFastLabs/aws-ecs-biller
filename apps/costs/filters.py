import django_filters as filters
from .models import LineItem, DailyCostAggregate, HourlyCostAggregate


class LineItemFilter(filters.FilterSet):
    usage_start_after = filters.DateTimeFilter(field_name="usage_start", lookup_expr="gte")
    usage_start_before = filters.DateTimeFilter(field_name="usage_start", lookup_expr="lte")
    tag_key = filters.CharFilter(method="filter_tag_key")
    tag_value = filters.CharFilter(method="filter_tag_value")

    def filter_tag_key(self, qs, name, value):
        return qs.filter(tags__has_key=value)

    def filter_tag_value(self, qs, name, value):
        key = self.data.get("tag_key", "")
        return qs.filter(tags__contains={key: value})

    class Meta:
        model = LineItem
        fields = ["service", "region", "linked_account_id", "line_item_type",
                  "instance_type", "billing_period"]


class DailyAggregateFilter(filters.FilterSet):
    date_after = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_before = filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = DailyCostAggregate
        fields = ["date", "linked_account_id", "service", "region", "line_item_type"]


class HourlyAggregateFilter(filters.FilterSet):
    hour_after = filters.DateTimeFilter(field_name="hour", lookup_expr="gte")
    hour_before = filters.DateTimeFilter(field_name="hour", lookup_expr="lte")

    class Meta:
        model = HourlyCostAggregate
        fields = ["linked_account_id", "service", "region", "line_item_type"]
