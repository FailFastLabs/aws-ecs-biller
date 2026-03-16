from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import SplittingRule, SplitResult
from .serializers import SplittingRuleSerializer, SplitResultSerializer


class SplittingRuleListCreateView(generics.ListCreateAPIView):
    queryset = SplittingRule.objects.all()
    serializer_class = SplittingRuleSerializer


class SplittingRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = SplittingRule.objects.all()
    serializer_class = SplittingRuleSerializer


class RunSplitView(APIView):
    def post(self, request, pk):
        from .services.splitter import run_split
        from .services.verifier import SplitInvariantViolationError
        rule = SplittingRule.objects.get(pk=pk)
        billing_period = request.data.get("billing_period", "")
        try:
            n = run_split(rule, billing_period)
            return Response({"created": n, "status": "ok"}, status=status.HTTP_201_CREATED)
        except SplitInvariantViolationError as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SplitResultListView(generics.ListAPIView):
    serializer_class = SplitResultSerializer

    def get_queryset(self):
        qs = SplitResult.objects.all()
        rule_id = self.request.query_params.get("rule_id")
        bp = self.request.query_params.get("billing_period")
        if rule_id:
            qs = qs.filter(splitting_rule_id=rule_id)
        if bp:
            qs = qs.filter(billing_period=bp)
        return qs


class VerifySplitView(APIView):
    def get(self, request):
        from .services.verifier import verify_split_invariant, SplitInvariantViolationError
        rule_id = request.query_params.get("rule_id")
        bp = request.query_params.get("billing_period", "")
        rule = SplittingRule.objects.get(pk=rule_id)
        try:
            verify_split_invariant(rule, bp)
            return Response({"status": "ok"})
        except SplitInvariantViolationError as e:
            return Response({"status": "violation", "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
