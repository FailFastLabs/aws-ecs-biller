import factory
from apps.accounts.models import AwsAccount, CurManifest


class AwsAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AwsAccount
        django_get_or_create = ("account_id",)

    account_id = factory.Sequence(lambda n: f"{100000000000 + n:012d}")
    account_name = factory.LazyAttribute(lambda o: f"account-{o.account_id}")
    is_payer = False


class CurManifestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CurManifest

    account = factory.SubFactory(AwsAccountFactory)
    s3_bucket = "test-cur-bucket"
    s3_prefix = "acme-cur"
    report_name = "acme-cur"
    time_unit = "HOURLY"
    compression = "GZIP"
    aws_region = "us-east-1"
