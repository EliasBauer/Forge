from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from general_manager.manager.general_manager import GeneralManager
from general_manager.permission import object_capability

from apps.authentication.permission import _is_in_group


def _user_or_none(user: object) -> AbstractBaseUser | None:
    """Nur eingeloggte User weiterreichen — AnonymousUser zählt als "kein User"."""
    if isinstance(user, AbstractBaseUser):
        return user
    return None


def _can_read(
    manager: type[GeneralManager],
    user: object,
    attribute: str | None = None,
) -> bool:
    """Fragt die Permission-Klasse des Managers im Klassen-Kontext.

    Damit ist die Capability per Konstruktion deckungsgleich mit dem, was die
    GraphQL-Queries tatsächlich liefern — statt die Regel mit Gruppennamen zu
    duplizieren.
    """
    permission = manager.Permission(manager, user)
    if attribute is None:
        return permission.check_operation_permission("read")
    return permission.check_permission("read", attribute)


def _can_create_projekt(_instance: object, user: object) -> bool:
    resolved = _user_or_none(user)
    if resolved is None:
        return False
    return _is_in_group(resolved, "Admin") or _is_in_group(resolved, "Projektleiter")


def _can_manage_stundensaetze(_instance: object, user: object) -> bool:
    resolved = _user_or_none(user)
    if resolved is None:
        return False
    return _is_in_group(resolved, "Admin") or _is_in_group(resolved, "Projektleiter")


def _can_view_finanzen(_instance: object, user: object) -> bool:
    from apps.projekt.models import Projekt

    return _can_read(Projekt, user, "offerte_summe")


def _can_view_kosten_positionen(_instance: object, user: object) -> bool:
    from apps.projekt.models import KostenPosition

    return _can_read(KostenPosition, user)


class CurrentUserCapabilities:
    graphql_fields: ClassVar[dict[str, type]] = {"username": str}
    graphql_capabilities = (
        object_capability("canCreateProjekt", _can_create_projekt),
        object_capability("canManageStundensaetze", _can_manage_stundensaetze),
        object_capability("canViewFinanzen", _can_view_finanzen),
        object_capability("canViewKostenPositionen", _can_view_kosten_positionen),
    )
