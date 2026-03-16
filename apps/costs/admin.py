from django.contrib import admin
from .models import (LineItem, DailyCostAggregate, HourlyCostAggregate,
                     EdpDiscount, SpotPriceHistory, InstancePricing)

admin.site.register(LineItem)
admin.site.register(DailyCostAggregate)
admin.site.register(HourlyCostAggregate)
admin.site.register(EdpDiscount)
admin.site.register(SpotPriceHistory)
admin.site.register(InstancePricing)
