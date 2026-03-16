from django.contrib import admin
from .models import CurDownloadJob, CurFile
admin.site.register(CurDownloadJob)
admin.site.register(CurFile)
