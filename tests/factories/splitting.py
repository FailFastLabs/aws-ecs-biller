import factory
from apps.splitting.models import SplittingRule


class SplittingRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SplittingRule

    name = factory.Sequence(lambda n: f"Rule {n}")
    service = "AmazonEKS"
    region = "us-east-1"
    split_by_tag_key = "user:team"
    weight_strategy = "custom_weight"
    custom_weights = {"backend": 0.40, "frontend": 0.35, "data": 0.25}
    active = True
