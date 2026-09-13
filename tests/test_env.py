from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from forge.env import env_bool, env_csv, env_int, env_secret


def test_env_bool_parses_truthy_and_falsy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAG", " Yes ")
    assert env_bool("FLAG") is True
    monkeypatch.setenv("FLAG", "off")
    assert env_bool("FLAG") is False
    monkeypatch.delenv("FLAG")
    assert env_bool("FLAG", True) is True


def test_env_bool_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAG", "maybe")
    with pytest.raises(ValueError, match="FLAG"):
        env_bool("FLAG")


def test_env_csv_strips_and_drops_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOSTS", " a.example , ,b.example")
    assert env_csv("HOSTS") == ["a.example", "b.example"]
    monkeypatch.delenv("HOSTS")
    assert env_csv("HOSTS", "x,y") == ["x", "y"]


def test_env_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N", "7")
    assert env_int("N", 1) == 7
    monkeypatch.delenv("N")
    assert env_int("N", 1) == 1
    monkeypatch.setenv("N", "x")
    with pytest.raises(ValueError, match="N"):
        env_int("N", 1)


def test_env_secret_prefers_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "s.txt"
    secret.write_text("from-file\n")
    monkeypatch.setenv("KEY", "from-env")
    monkeypatch.setenv("KEY_FILE", str(secret))
    assert env_secret("KEY") == "from-file"
    monkeypatch.delenv("KEY_FILE")
    assert env_secret("KEY") == "from-env"
    monkeypatch.delenv("KEY")
    assert env_secret("KEY", default="d") == "d"
    assert env_secret("KEY") == ""


def test_env_secret_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEY", raising=False)
    monkeypatch.delenv("KEY_FILE", raising=False)
    with pytest.raises(ImproperlyConfigured, match="KEY oder KEY_FILE"):
        env_secret("KEY", required=True)
