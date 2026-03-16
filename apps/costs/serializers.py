from rest_framework import serializers
from .models import (LineItem, DailyCostAggregate, HourlyCostAggregate,
                     EdpDiscount, SpotPriceHistory, InstancePricing)


class LineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LineItem
        fields = "__all__"


class DailyCostAggregateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyCostAggregate
        fields = "__all__"


class HourlyCostAggregateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourlyCostAggregate
        fields = "__all__"


class EdpDiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = EdpDiscount
        fields = "__all__"


class SpotPriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SpotPriceHistory
        fields = "__all__"


class InstancePricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstancePricing
        fields = "__all__"
