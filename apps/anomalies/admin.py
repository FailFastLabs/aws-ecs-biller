from django.contrib import admin
from .models import AnomalyDetectionRun, CostAnomaly
admin.site.register(AnomalyDetectionRun)
admin.site.register(CostAnomaly)
