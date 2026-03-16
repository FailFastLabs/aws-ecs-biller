from rest_framework import serializers
from .models import AwsAccount, CurManifest

class AwsAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = AwsAccount
        fields = "__all__"

class CurManifestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurManifest
        fields = "__all__"
