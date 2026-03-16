from django.contrib import admin
from .models import ReservedInstance, SavingsPlan, RiRecommendation
admin.site.register(ReservedInstance)
admin.site.register(SavingsPlan)
admin.site.register(RiRecommendation)
