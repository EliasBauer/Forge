"""Umgebungs-Helfer für Settings: Docker-Secrets (`NAME_FILE`) vor `NAME`."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ValueError(f"{name} muss ein boolescher Wert sein")


def env_csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} muss eine ganze Zahl sein") from exc


def env_secret(name: str, *, default: str | None = None, required: bool = False) -> str:
    file_name = os.environ.get(f"{name}_FILE")
    if file_name:
        value: str | None = Path(file_name).read_text().strip()
    else:
        value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"{name} oder {name}_FILE muss gesetzt sein")
    return value or ""
