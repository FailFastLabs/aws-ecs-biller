from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.web.urls")),
    path("api/v1/", include("apps.costs.urls")),
    path("api/v1/", include("apps.reservations.urls")),
    path("api/v1/", include("apps.forecasting.urls")),
    path("api/v1/", include("apps.anomalies.urls")),
    path("api/v1/", include("apps.splitting.urls")),
    path("api/v1/viz/", include("apps.visualizations.urls")),
    path("api/v1/", include("apps.ingestion.urls")),
    path("api/v1/", include("apps.accounts.urls")),
]
