from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Verify cost split invariant for a billing period"

    def add_arguments(self, parser):
        parser.add_argument("billing_period", type=str)

    def handle(self, *args, **options):
        from apps.splitting.models import SplittingRule
        from apps.splitting.services.verifier import verify_split_invariant, SplitInvariantViolationError

        for rule in SplittingRule.objects.filter(active=True):
            try:
                verify_split_invariant(rule, options["billing_period"])
                self.stdout.write(self.style.SUCCESS(f"Rule {rule.name}: PASS"))
            except SplitInvariantViolationError as e:
                self.stdout.write(self.style.ERROR(f"Rule {rule.name}: FAIL\n{e}"))
