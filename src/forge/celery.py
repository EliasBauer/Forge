import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "forge.settings")

app = Celery("forge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
# forge.observability ist keine Django-App; Tasks explizit einsammeln.
app.autodiscover_tasks(["forge.observability"])
