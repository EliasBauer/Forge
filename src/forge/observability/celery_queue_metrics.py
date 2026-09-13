"""Queue-Tiefe und Alter der aeltesten Nachricht je Celery-Queue (Pushgateway)."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping, MutableMapping
from numbers import Real
from typing import Any, Final, Protocol, cast

import redis
import requests
from celery.signals import before_task_publish
from django.conf import settings

QUEUES: Final = ("default", "search.reconciliation")
_PUBLISHED_AT_HEADER: Final = "forge_published_at"
_PUSH_JOB: Final = "forge_celery_queues"


class RedisQueueClient(Protocol):
    def llen(self, queue: str) -> int: ...

    def lindex(self, queue: str, index: int) -> bytes | str | None: ...


@before_task_publish.connect(  # type: ignore[untyped-decorator]
    dispatch_uid="forge.observability.celery_queue_metrics.publish_timestamp"
)
def stamp_task_publish(
    sender: object | None = None,
    *,
    headers: MutableMapping[str, object] | None = None,
    **kwargs: Any,
) -> None:
    if headers is not None:
        headers[_PUBLISHED_AT_HEADER] = time.time()


def _published_at(message: bytes | str | None) -> float | None:
    if message is None:
        return None
    try:
        payload = json.loads(message)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    headers = payload.get("headers")
    if not isinstance(headers, Mapping):
        return None
    value = headers.get(_PUBLISHED_AT_HEADER)
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    published_at = float(value)
    return published_at if math.isfinite(published_at) else None


def collect_queue_metrics(
    redis_client: RedisQueueClient,
    *,
    now: float | None = None,
) -> str:
    collected_at = time.time() if now is None else now
    lines: list[str] = []
    for queue in QUEUES:
        depth = max(int(redis_client.llen(queue)), 0)
        lines.append(f'forge_celery_queue_depth{{queue="{queue}"}} {depth}')
        if depth == 0:
            continue
        published_at = _published_at(redis_client.lindex(queue, -1))
        if published_at is not None:
            age = max(collected_at - published_at, 0.0)
            lines.append(
                f'forge_celery_oldest_task_age_seconds{{queue="{queue}"}} {age:g}'
            )
    return "\n".join(lines) + "\n"


def publish_observability_queue_metrics() -> None:
    gateway = str(getattr(settings, "PUSHGATEWAY_URL", "")).strip()
    if not gateway:
        return
    try:
        redis_client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        metrics = collect_queue_metrics(cast(RedisQueueClient, redis_client))
        response = requests.put(
            f"{gateway.rstrip('/')}/metrics/job/{_PUSH_JOB}",
            data=metrics,
            timeout=5,
        )
        response.raise_for_status()
    except (
        requests.RequestException,
        redis.exceptions.RedisError,
        TypeError,
        ValueError,
        UnicodeError,
    ):
        return
