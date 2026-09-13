import json
import os
import subprocess
import sys
from pathlib import Path

from forge import celery_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUEUE_METRICS_TASK = "forge.observability.tasks.publish_observability_queue_metrics"


def test_celery_app_exports_task_events_and_default_queue() -> None:
    assert celery_app.main == "forge"
    assert celery_app.conf.task_default_queue == "default"
    assert celery_app.conf.worker_send_task_events is True
    assert celery_app.conf.task_send_sent_event is True
    assert "publish-observability-queue-metrics" not in celery_app.conf.beat_schedule


def test_queue_metrics_task_is_registered() -> None:
    celery_app.loader.import_default_modules()
    assert QUEUE_METRICS_TASK in celery_app.tasks


def test_production_beat_schedules_queue_metrics_every_minute() -> None:
    env = {
        **os.environ,
        "FORGE_ENV": "production",
        "DJANGO_SECRET_KEY": "test-only-secret-key-0123456789",
        "POSTGRES_PASSWORD": "test",
        "PYTHONPATH": str(REPOSITORY_ROOT / "src"),
    }
    code = (
        "import json, django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', "
        "'forge.settings'); from forge import celery_app; "
        "print(json.dumps(celery_app.conf.beat_schedule.get("
        "'publish-observability-queue-metrics')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPOSITORY_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "task": QUEUE_METRICS_TASK,
        "schedule": 60.0,
    }
