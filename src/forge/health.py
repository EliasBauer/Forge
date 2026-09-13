"""Liveness/Readiness für Docker-Healthchecks, deploy.sh und Blackbox-Probes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_cache() -> None:
    cache.set("forge-readiness", "ok", timeout=5)
    if cache.get("forge-readiness") != "ok":
        raise RuntimeError("cache roundtrip failed")


def _outcome(check: Callable[[], None]) -> str:
    try:
        check()
    except Exception:  # noqa: BLE001 - jede Stoerung bedeutet "nicht bereit"
        return "error"
    return "ok"


def live(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def ready(_request: HttpRequest) -> JsonResponse:
    checks = {
        "database": _outcome(_check_database),
        "cache": _outcome(_check_cache),
    }
    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=200 if healthy else 503,
    )


def maintenance(_request: HttpRequest) -> JsonResponse:
    enabled = Path(settings.MAINTENANCE_FLAG_FILE).exists()
    return JsonResponse({"maintenance": enabled}, status=503 if enabled else 200)
