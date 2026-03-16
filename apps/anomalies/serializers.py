from rest_framework import serializers
from .models import AnomalyDetectionRun, CostAnomaly


class AnomalyDetectionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnomalyDetectionRun
        fields = "__all__"


class CostAnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = CostAnomaly
        fields = "__all__"
