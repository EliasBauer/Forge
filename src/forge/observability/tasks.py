from celery import shared_task

from forge.observability.celery_queue_metrics import (
    publish_observability_queue_metrics as publish_queue_metrics,
)


@shared_task(name="forge.observability.tasks.publish_observability_queue_metrics")  # type: ignore[untyped-decorator]
def publish_observability_queue_metrics() -> None:
    publish_queue_metrics()
