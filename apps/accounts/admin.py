from django.contrib import admin
from .models import AwsAccount, CurManifest

admin.site.register(AwsAccount)
admin.site.register(CurManifest)
