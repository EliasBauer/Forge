from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import redis
import requests

from forge.observability import celery_queue_metrics
from forge.observability.celery_queue_metrics import (
    collect_queue_metrics,
    stamp_task_publish,
)


class FakeRedis:
    def __init__(self, queues: dict[str, list[bytes]]) -> None:
        self._queues = queues

    def llen(self, queue: str) -> int:
        return len(self._queues.get(queue, []))

    def lindex(self, queue: str, index: int) -> bytes | None:
        items = self._queues.get(queue, [])
        return items[index] if items else None


def test_queue_metrics_report_depth_and_oldest_message_age() -> None:
    client = FakeRedis(
        {"default": [json.dumps({"headers": {"forge_published_at": 100}}).encode()]}
    )
    metrics = collect_queue_metrics(client, now=150)
    assert 'forge_celery_queue_depth{queue="default"} 1' in metrics
    assert 'forge_celery_oldest_task_age_seconds{queue="default"} 50' in metrics


def test_empty_queues_report_zero_depth_without_age() -> None:
    metrics = collect_queue_metrics(FakeRedis({}), now=150)
    assert 'forge_celery_queue_depth{queue="default"} 0' in metrics
    assert 'forge_celery_queue_depth{queue="search.reconciliation"} 0' in metrics
    assert "forge_celery_oldest_task_age_seconds" not in metrics


def test_collect_uses_wall_clock_when_now_is_omitted() -> None:
    metrics = collect_queue_metrics(
        FakeRedis({"default": [b'{"headers": {"forge_published_at": 1}}']})
    )
    assert 'forge_celery_queue_depth{queue="default"} 1' in metrics
    assert "forge_celery_oldest_task_age_seconds" in metrics


@pytest.mark.parametrize(
    "message",
    [
        b"not-json",
        b"[]",
        b"{}",
        b'{"headers": []}',
        b'{"headers": {}}',
        b'{"headers": {"forge_published_at": true}}',
        b'{"headers": {"forge_published_at": "old"}}',
        b'{"headers": {"forge_published_at": NaN}}',
    ],
)
def test_invalid_oldest_message_does_not_fabricate_age(message: bytes) -> None:
    metrics = collect_queue_metrics(FakeRedis({"default": [message]}), now=150)
    assert 'forge_celery_queue_depth{queue="default"} 1' in metrics
    assert "forge_celery_oldest_task_age_seconds" not in metrics


def test_missing_oldest_message_does_not_fabricate_age() -> None:
    class DepthOnlyRedis(FakeRedis):
        def lindex(self, queue: str, index: int) -> bytes | None:
            return None

    metrics = collect_queue_metrics(DepthOnlyRedis({"default": [b"x"]}), now=150)
    assert "forge_celery_oldest_task_age_seconds" not in metrics


def test_queue_age_is_clamped_when_publish_time_is_in_the_future() -> None:
    metrics = collect_queue_metrics(
        FakeRedis({"default": [b'{"headers": {"forge_published_at": 200}}']}), now=150
    )
    assert 'forge_celery_oldest_task_age_seconds{queue="default"} 0' in metrics


def test_publish_stamps_headers_and_ignores_missing_headers() -> None:
    headers: dict[str, object] = {}
    stamp_task_publish(headers=headers)
    assert isinstance(headers["forge_published_at"], float)
    stamp_task_publish(headers=None)


def _configure(monkeypatch: pytest.MonkeyPatch, gateway: str) -> tuple[Mock, Mock]:
    monkeypatch.setattr(
        celery_queue_metrics,
        "settings",
        SimpleNamespace(
            PUSHGATEWAY_URL=gateway, CELERY_BROKER_URL="redis://redis:6379/0"
        ),
    )
    from_url = Mock(return_value=FakeRedis({}))
    monkeypatch.setattr(redis.Redis, "from_url", from_url)
    put = Mock(return_value=Mock(raise_for_status=Mock()))
    monkeypatch.setattr(requests, "put", put)
    return from_url, put


def test_publish_is_skipped_without_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    from_url, put = _configure(monkeypatch, "  ")
    celery_queue_metrics.publish_observability_queue_metrics()
    from_url.assert_not_called()
    put.assert_not_called()


def test_publish_puts_snapshot_to_pushgateway_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from_url, put = _configure(monkeypatch, " http://pushgateway:9091/ ")
    celery_queue_metrics.publish_observability_queue_metrics()
    from_url.assert_called_once_with(
        "redis://redis:6379/0", socket_connect_timeout=5, socket_timeout=5
    )
    put.assert_called_once()
    assert (
        put.call_args.args[0]
        == "http://pushgateway:9091/metrics/job/forge_celery_queues"
    )
    assert put.call_args.kwargs["timeout"] == 5
    assert 'forge_celery_queue_depth{queue="default"} 0' in put.call_args.kwargs["data"]


def test_publish_is_best_effort_for_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _from_url, put = _configure(monkeypatch, "http://pushgateway:9091")
    put.side_effect = requests.RequestException("unavailable")
    celery_queue_metrics.publish_observability_queue_metrics()


def test_publish_is_best_effort_for_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from_url, put = _configure(monkeypatch, "http://pushgateway:9091")
    from_url.side_effect = redis.exceptions.TimeoutError("slow")
    celery_queue_metrics.publish_observability_queue_metrics()
    put.assert_not_called()


def test_celery_task_delegates_to_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    from forge.observability import tasks

    publish = Mock()
    monkeypatch.setattr(tasks, "publish_queue_metrics", publish)
    tasks.publish_observability_queue_metrics()
    publish.assert_called_once_with()
