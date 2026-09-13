from pathlib import Path

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


def test_live_needs_no_dependencies() -> None:
    response = Client().get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_and_cache() -> None:
    response = Client().get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "cache": "ok"},
    }


def test_ready_reports_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from forge import health

    def broken() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(health, "_check_database", broken)
    response = Client().get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "error"


def test_ready_reports_cache_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from forge import health

    def broken() -> None:
        raise RuntimeError("cache down")

    monkeypatch.setattr(health, "_check_cache", broken)
    response = Client().get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["checks"]["cache"] == "error"


def test_cache_check_detects_missing_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    from forge import health

    monkeypatch.setattr(cache, "get", lambda _key: None)
    with pytest.raises(RuntimeError, match="cache roundtrip"):
        health._check_cache()


def test_maintenance_reflects_flag_file(tmp_path: Path) -> None:
    flag = tmp_path / "maintenance"
    with override_settings(MAINTENANCE_FLAG_FILE=str(flag)):
        assert Client().get("/health/maintenance/").status_code == 200
        flag.write_text("maintenance")
        response = Client().get("/health/maintenance/")
    assert response.status_code == 503
    assert response.json() == {"maintenance": True}


def test_metrics_endpoint_is_exposed() -> None:
    response = Client().get("/metrics")
    assert response.status_code == 200
    assert b"django_http_requests_total" in response.content
