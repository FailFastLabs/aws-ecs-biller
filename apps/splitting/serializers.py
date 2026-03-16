from rest_framework import serializers
from .models import SplittingRule, SplitResult


class SplittingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SplittingRule
        fields = "__all__"


class SplitResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SplitResult
        fields = "__all__"
