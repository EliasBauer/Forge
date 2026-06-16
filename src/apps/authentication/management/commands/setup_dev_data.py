from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)

GROUPS = ["Admin", "Projektleiter", "Betrachter", "Monteur"]

USERS: list[dict[str, Any]] = [
    {
        "username": "admin",
        "password": "admin",
        "is_superuser": True,
        "is_staff": True,
        "group": "Admin",
    },
    {
        "username": "simon",
        "password": "simon",
        "is_superuser": False,
        "is_staff": False,
        "group": "Projektleiter",
    },
    {
        "username": "tina",
        "password": "tina",
        "is_superuser": False,
        "is_staff": False,
        "group": "Betrachter",
    },
]


class Command(BaseCommand):
    help = "Bootstrap der Dev-Daten: Gruppen, User, Bexio-Sync (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        self._setup_groups()
        self._setup_users()
        self._run_bexio_sync()

    def _setup_groups(self) -> None:
        with transaction.atomic():
            for name in GROUPS:
                _, created = Group.objects.get_or_create(name=name)
                marker = "angelegt" if created else "vorhanden"
                self.stdout.write(f"Gruppe '{name}': {marker}")

    def _setup_users(self) -> None:
        with transaction.atomic():
            for spec in USERS:
                user, created = User.objects.get_or_create(
                    username=spec["username"],
                )
                user.is_superuser = spec["is_superuser"]
                user.is_staff = spec["is_staff"]
                user.set_password(spec["password"])
                user.save()

                group = Group.objects.get(name=spec["group"])
                user.groups.set([group])

                marker = "angelegt" if created else "aktualisiert"
                self.stdout.write(
                    f"User '{spec['username']}' ({spec['group']}): {marker}"
                )

    def _run_bexio_sync(self) -> None:
        from apps.bexio.sync import sync_konten, sync_lieferantenrechnungen

        try:
            count = sync_konten()
            self.stdout.write(f"Bexio: {count} Konten synchronisiert")
        except Exception:
            logger.exception("Bexio-Konten-Sync fehlgeschlagen")
            self.stdout.write(self.style.WARNING("Bexio-Konten-Sync fehlgeschlagen"))

        try:
            count = sync_lieferantenrechnungen()
            self.stdout.write(
                f"Bexio: {count} Lieferantenrechnungs-Zeilen synchronisiert"
            )
        except Exception:
            logger.exception("Bexio-Lieferantenrechnungs-Sync fehlgeschlagen")
            self.stdout.write(
                self.style.WARNING("Bexio-Lieferantenrechnungs-Sync fehlgeschlagen")
            )
