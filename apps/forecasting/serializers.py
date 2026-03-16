from rest_framework import serializers
from .models import ForecastRun, ForecastPoint


class ForecastPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForecastPoint
        fields = "__all__"


class ForecastRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForecastRun
        fields = "__all__"
