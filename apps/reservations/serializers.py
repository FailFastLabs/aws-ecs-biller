from rest_framework import serializers
from .models import ReservedInstance, SavingsPlan, RiRecommendation


class ReservedInstanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservedInstance
        fields = "__all__"


class SavingsPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsPlan
        fields = "__all__"


class RiRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiRecommendation
        fields = "__all__"
