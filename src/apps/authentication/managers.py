from __future__ import annotations

from django.contrib.auth.models import Group, User
from django.db.models import Model
from general_manager import (
    AdditiveManagerPermission,
    ExistingModelInterface,
    GeneralManager,
)
from general_manager.interface.utils.history import DatabaseAwareHistoricalRecords
from simple_history import register


def _register_history_if_needed(model: type[Model]) -> None:
    """Registriert simple_history für `model`, falls noch nicht geschehen.

    Der hasattr-Guard verhindert doppelte Registrierung bei einem
    Modul-Reimport (z. B. Django-Autoreload im Dev-Server) — ein erneuter
    `register()`-Aufruf für ein bereits registriertes Model schlägt fehl.
    """
    if not hasattr(model._meta, "simple_history_manager_attribute"):
        register(
            model,
            app="apps.authentication",
            m2m_fields=[f.name for f in model._meta.local_many_to_many],
            records_class=DatabaseAwareHistoricalRecords,
            use_base_model_db=True,
            excluded_fields=["password"] if model is User else [],
        )


# Muss vor den Manager-Klassendefinitionen laufen: registriert die History
# BEIDER Django-Modelle unter dem "apps.authentication"-App-Label. Ohne das
# würde GMs eigene History-Registrierung greifen (ensure_history() läuft für
# JEDEN ExistingModelInterface-Manager automatisch) und die Historical*-
# Modelle fälschlich unter dem "auth"-App-Label landen — dort dürfen wir
# keine eigene Migration ablegen (makemigrations würde sonst versuchen, in
# django/contrib/auth/migrations/ innerhalb der installierten Bibliothek zu
# schreiben).
for _model in (User, Group):
    _register_history_if_needed(_model)


class Gruppe(GeneralManager):
    """GM-Wrapper um django.contrib.auth.models.Group.

    Nötig, damit Benutzer.groups_list als echte, filterbare Relation (nicht
    als String-Skalar) im GraphQL-Schema erscheint — GM löst Relationsfelder
    nur zu einem Objekttyp auf, wenn das Zielmodell selbst ein registrierter
    GM-Manager ist.
    """

    id: int
    name: str

    class Interface(ExistingModelInterface[Group]):
        model = Group

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["never"]
        __update__ = ["never"]
        __delete__ = ["never"]


class Benutzer(GeneralManager):
    """GM-Wrapper um django.contrib.auth.models.User.

    model = User (direkte Klasse), NICHT settings.AUTH_USER_MODEL (String):
    Letzteres löst apps.get_model() zur Klassendefinitionszeit aus, was
    mypys django-stubs-Plugin mit AppRegistryNotReady crasht (verifiziert).
    """

    id: int
    username: str
    is_active: bool

    class Interface(ExistingModelInterface[User]):
        model = User

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["never"]
        __update__ = ["never"]
        __delete__ = ["never"]
        password = {"read": ["never"]}
        is_superuser = {"read": ["isForgeAdmin"]}
        user_permissions_list = {"read": ["isForgeAdmin"]}
        log_entry_list = {"read": ["isForgeAdmin"]}
        is_staff = {"read": ["isForgeAdmin"]}
        email = {"read": ["isForgeAdmin"]}
        first_name = {"read": ["isForgeAdmin"]}
        last_name = {"read": ["isForgeAdmin"]}
        last_login = {"read": ["isForgeAdmin"]}
        date_joined = {"read": ["isForgeAdmin"]}
