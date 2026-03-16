from rest_framework import serializers
from .models import CurDownloadJob, CurFile

class CurDownloadJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurDownloadJob
        fields = "__all__"

class CurFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurFile
        fields = "__all__"
