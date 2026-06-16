from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

GROUPS = ["Admin", "Projektleiter", "Betrachter", "Monteur"]


class Command(BaseCommand):
    help = "Legt die vier Standard-Benutzergruppen an (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        for name in GROUPS:
            _, created = Group.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f"Gruppe '{name}' angelegt.")
            else:
                self.stdout.write(f"Gruppe '{name}' existiert bereits.")
