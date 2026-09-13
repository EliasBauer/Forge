from django.contrib import admin
from django.urls import include, path

from forge import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.authentication.urls")),
    path("health/live/", health.live, name="health-live"),
    path("health/ready/", health.ready, name="health-ready"),
    path("health/maintenance/", health.maintenance, name="health-maintenance"),
    # /metrics (django-prometheus); nginx proxied den Pfad bewusst nicht
    path("", include("django_prometheus.urls")),
]
