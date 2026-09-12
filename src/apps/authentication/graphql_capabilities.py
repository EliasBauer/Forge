from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from general_manager.permission import object_capability

from apps.authentication.permission import _is_in_group


def _user_or_none(user: object) -> AbstractBaseUser | None:
    """Nur eingeloggte User weiterreichen — AnonymousUser zählt als "kein User".

    Ohne diese Schranke wäre canViewFinanzen für nicht eingeloggte Requests
    fälschlich True (die "not Monteur"-Regel greift für AnonymousUser sonst
    versehentlich positiv). Das Frontend prüfte das bisher explizit über
    `user !== null &&`.
    """
    if isinstance(user, AbstractBaseUser):
        return user
    return None


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
    resolved = _user_or_none(user)
    if resolved is None:
        return False
    return not _is_in_group(resolved, "Monteur")


class CurrentUserCapabilities:
    graphql_fields: ClassVar[dict[str, type]] = {"username": str}
    graphql_capabilities = (
        object_capability("canCreateProjekt", _can_create_projekt),
        object_capability("canManageStundensaetze", _can_manage_stundensaetze),
        object_capability("canViewFinanzen", _can_view_finanzen),
    )
