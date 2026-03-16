from rest_framework.routers import DefaultRouter
from .views import CurDownloadJobViewSet, CurFileViewSet

router = DefaultRouter()
router.register("ingestion/jobs", CurDownloadJobViewSet)
router.register("ingestion/files", CurFileViewSet)
urlpatterns = router.urls
