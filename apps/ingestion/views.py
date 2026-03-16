from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CurDownloadJob, CurFile
from .serializers import CurDownloadJobSerializer, CurFileSerializer


class CurDownloadJobViewSet(viewsets.ModelViewSet):
    queryset = CurDownloadJob.objects.all()
    serializer_class = CurDownloadJobSerializer

    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger(self, request, pk=None):
        from .tasks import download_cur_task, run_etl_task
        job = self.get_object()
        chain = download_cur_task.s(job.id) | run_etl_task.s()
        result = chain.delay()
        return Response({"task_id": result.id, "status": "queued"})


class CurFileViewSet(viewsets.ModelViewSet):
    queryset = CurFile.objects.all()
    serializer_class = CurFileSerializer
