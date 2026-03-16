import boto3
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AwsAccount, CurManifest
from .serializers import AwsAccountSerializer, CurManifestSerializer


class AwsAccountViewSet(viewsets.ModelViewSet):
    queryset = AwsAccount.objects.all()
    serializer_class = AwsAccountSerializer

    @action(detail=True, methods=["post"], url_path="test-credentials")
    def test_credentials(self, request, pk=None):
        account = self.get_object()
        try:
            session = boto3.Session()
            if account.iam_role_arn:
                sts = session.client("sts")
                creds = sts.assume_role(
                    RoleArn=account.iam_role_arn,
                    RoleSessionName="cur-analyzer-test",
                )["Credentials"]
                session = boto3.Session(
                    aws_access_key_id=creds["AccessKeyId"],
                    aws_secret_access_key=creds["SecretAccessKey"],
                    aws_session_token=creds["SessionToken"],
                )
            identity = session.client("sts").get_caller_identity()
            return Response({"status": "ok", "account_id": identity["Account"]})
        except Exception as exc:
            return Response({"status": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CurManifestViewSet(viewsets.ModelViewSet):
    queryset = CurManifest.objects.all()
    serializer_class = CurManifestSerializer
