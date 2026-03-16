from rest_framework.routers import DefaultRouter
from .views import AwsAccountViewSet, CurManifestViewSet

router = DefaultRouter()
router.register("accounts", AwsAccountViewSet)
router.register("manifests", CurManifestViewSet)
urlpatterns = router.urls
