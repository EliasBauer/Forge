# Benutzer als GM-Type + GraphQL-Capabilities — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Benutzer`/`Gruppe` als vollwertige GM-Manager (wrappen `auth.User`/`auth.Group`), Objekt-Capabilities auf `Projekt` (`canUpdate`/`canDelete`) und globale Capabilities über `me` (`canCreateProjekt`/`canManageStundensaetze`/`canViewFinanzen`) — als Ersatz für die gruppenbasierte Permission-Logik im Frontend.

**Architecture:** Zwei neue GM-Manager (`Benutzer`, `Gruppe`, `ExistingModelInterface`) plus zwei unabhängige GM-Capability-Mechanismen (`Permission.graphql_capabilities` pro Objekt, `GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER` für `me`). Frontend liest Berechtigungen ausschließlich über GraphQL; REST-Endpunkte `/api/me/` und `/api/users/` sowie `frontend/src/utils/permissions.ts` entfallen.

**Tech Stack:** Django 6 + GeneralManager 0.79.3 + graphene-django (Backend), React + TypeScript + Apollo Client (Frontend), django-simple-history.

**Spec:** `docs/superpowers/specs/2026-09-10-benutzer-gm-capabilities-design.md`

## Global Constraints

- Kein Custom-`AUTH_USER_MODEL`. `Benutzer.Interface.model = User` (**direkter Klassen-Import, NICHT `settings.AUTH_USER_MODEL`** — siehe Korrektur unten).
- Kein GraphQL-Create/Update/Delete für `Benutzer`/`Gruppe` (`__create__ = __update__ = __delete__ = ["never"]`).
- `login_view`/`logout_view` bleiben REST (Session-Cookie); nur `/api/me/` und `/api/users/` werden ersetzt.
- `password` auf `Benutzer` ist für **niemanden** über GraphQL lesbar (`{"read": ["never"]}`), auch nicht für Admins.
- Jede Task muss am Ende `pytest`/`vitest` grün und (für Backend-Tasks) `mypy src tests` fehlerfrei hinterlassen — siehe die zwei mypy-Korrekturen unten, die dafür zwingend sind.

## Korrekturen gegenüber der Spec (beim Plan-Verifizieren gefunden, real gegen den Code getestet)

Diese vier Punkte weichen von der Spec ab bzw. konkretisieren sie. Ohne sie bricht entweder `mypy`, `makemigrations` schreibt in `.venv` (!), oder bestehende Tests werden rot, ohne dass die Spec das vorhersagt:

1. **`Benutzer.Interface.model = User` (Klasse), nicht `settings.AUTH_USER_MODEL` (String).**
   Reproduziert: mit dem String crasht `mypy src tests` mit `INTERNAL ERROR — Error constructing plugin instance of NewSemanalDjangoPlugin` (`AppRegistryNotReady`). Grund: `apps.get_model()` wird nur für den String-Pfad aufgerufen, das braucht den vollständig geladenen App-Registry — django-stubs importiert Model-Module aber in einer Reihenfolge, in der das noch nicht der Fall ist. Mit `model = User` (direkte Klasse) entfällt der `apps.get_model()`-Aufruf komplett, kein Crash.
2. **`Gruppe` braucht dieselbe History-Vorregistrierung wie `Benutzer`.** Ohne das versucht `makemigrations`, `HistoricalGroup` nach `.venv/lib/.../django/contrib/auth/migrations/` zu schreiben (!) — reproduziert. Grund: GMs `ensure_history()` läuft für **jeden** `ExistingModelInterface`-Manager automatisch, nicht nur für `Benutzer`.
3. **`Projekt.Permission.graphql_capabilities = (...)` gehört in `ProjektConfig.ready()`, nicht auf Modulebene von `projekt.py`.** Reproduziert: auf Modulebene crasht `mypy src tests` mit demselben `INTERNAL ERROR` (`Projekt.Permission`-Zugriff löst GMs Lazy-Attribute-Init aus, die wieder den vollen App-Registry braucht). In `ready()` (läuft garantiert nach allen App-Imports, wird von django-stubs nicht mitausgeführt) ist es unproblematisch.
4. **Allein das *Definieren* von `Benutzer` ändert `Projekt.projektleiter` global** — nicht erst das Umtypen der Annotation in `projekt.py`. Reproduziert: mit nur `Benutzer`/`Gruppe` (Task 1), **ohne** `projekt.py` berührt zu haben, wurden bereits 9 Tests rot (`test_projekt.py::test_create_mit_projektleiter_als_string_id` u. a., `tests/test_graphql_queries.py` — bare `projektleiter` im Query-String wird zum Schema-Fehler, `.pk` auf dem zurückgegebenen `Benutzer`-Objekt existiert nicht). Grund: GM erkennt anhand des zugrundeliegenden Django-Models (nicht anhand der Typannotation), dass es einen registrierten Wrapper gibt, und wrapped **jede** FK auf `auth.User` automatisch — app-weit, nicht nur dort, wo die Annotation geändert wurde. Deshalb müssen die Fixes an `test_projekt.py` (`.pk`→`.id`) und `tests/test_graphql_queries.py` (`projektleiter` → `projektleiter { id username }`) bereits in **Task 1** passieren, nicht erst in der Projekt-Capabilities-Task — sonst ist Task 1 alleine nicht grün.

---

## Task 1: Benutzer & Gruppe GM-Manager + Permissions + Migration

**Files:**
- Create: `src/apps/authentication/models.py`
- Create: `src/apps/authentication/managers.py`
- Create: `src/apps/authentication/migrations/__init__.py`
- Create: `src/apps/authentication/migrations/0001_initial.py`
- Modify: `src/apps/authentication/permission.py` (neues `"never"`-Prädikat)
- Modify: `src/apps/authentication/apps.py` (`ready()` importiert `managers`)
- Modify: `src/apps/projekt/tests/test_projekt.py` (Seiteneffekt von `Benutzer`, s. o.)
- Modify: `tests/test_graphql_queries.py` (Seiteneffekt von `Benutzer`, s. o.)
- Test: `src/apps/authentication/tests/test_authentication.py` (neuer Test für `"never"`)
- Test: `src/apps/authentication/tests/test_benutzer.py` (neu)
- Test: `src/apps/authentication/tests/test_gruppe.py` (neu)

**Interfaces:**
- Produces: `Benutzer` (`apps.authentication.managers.Benutzer`, GM-Manager mit `id: int`, `username: str`, `is_active: bool`), `Gruppe` (`apps.authentication.managers.Gruppe`, GM-Manager mit `id: int`, `name: str`), `_permission_never` (`apps.authentication.permission`)
- Consumes: nichts aus anderen Tasks (Fundament-Task)

---

- [ ] **Step 1: Failing test für das `"never"`-Prädikat schreiben**

In `src/apps/authentication/tests/test_authentication.py`, Import-Zeile ergänzen und eine neue Test-Klasse direkt nach `PermissionIsMonteurTest` einfügen:

```python
from apps.authentication.permission import (
    _permission_is_admin,
    _permission_is_mechanic,
    _permission_is_project_leader,
    _permission_is_viewer,
    _permission_never,
)
```

```python
class PermissionNeverTest(TestCase):
    def test_returns_false_immer(self) -> None:
        self.assertFalse(_permission_never(MagicMock(), _make_user("Admin"), []))
        self.assertFalse(_permission_never(MagicMock(), _make_user(None), []))
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_authentication.py::PermissionNeverTest -v`
Expected: FAIL mit `ImportError: cannot import name '_permission_never'`

- [ ] **Step 3: `"never"`-Prädikat implementieren**

In `src/apps/authentication/permission.py`, direkt vor `@register_permission("isMonteur")` einfügen:

```python
@register_permission("never")
def _permission_never(
    _instance: PermissionDataManager[Any] | GeneralManager | GeneralManagerMeta,
    _user: AbstractBaseUser | AnonymousUser,
    _config: list[str],
) -> bool:
    return False
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_authentication.py::PermissionNeverTest -v`
Expected: PASS

- [ ] **Step 5: Failing GraphQL-Tests für `Benutzer`/`Gruppe` schreiben**

Neue Datei `src/apps/authentication/tests/test_benutzer.py`:

```python
"""GraphQL-Tests für den Benutzer-GM-Manager (apps.authentication.managers)."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase

GRAPHQL_URL = "/graphql/"


def _gql(
    client: Any, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    response = client.post(
        GRAPHQL_URL, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, (
        f"HTTP {response.status_code}: {response.content[:500]}"
    )
    data: dict[str, Any] = response.json()
    return data


_QUERY_BENUTZER = """
    query BenutzerDetail($id: ID!) {
      benutzer(id: $id) {
        id
        username
        password
        isSuperuser
        userPermissionsList
        logEntryList
      }
    }
"""


class BenutzerFieldVisibilityTest(TestCase):
    def setUp(self) -> None:
        self.target = User.objects.create_user(username="ziel", password="geheim123")

    def _login_as(self, username: str, groups: list[str]) -> None:
        user = User.objects.create_user(username, password="x")
        for name in groups:
            group, _ = Group.objects.get_or_create(name=name)
            user.groups.add(group)
        self.client.force_login(user)

    def test_password_ist_fuer_betrachter_null(self) -> None:
        self._login_as("betrachter1", ["Betrachter"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertIsNone(result["data"]["benutzer"]["password"])

    def test_password_ist_auch_fuer_admin_null(self) -> None:
        self._login_as("admin1", ["Admin"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertIsNone(result["data"]["benutzer"]["password"])

    def test_is_superuser_nur_fuer_admin_sichtbar(self) -> None:
        self._login_as("admin2", ["Admin"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertIsNotNone(result["data"]["benutzer"]["isSuperuser"])
        self.assertIsNotNone(result["data"]["benutzer"]["userPermissionsList"])
        self.assertIsNotNone(result["data"]["benutzer"]["logEntryList"])

    def test_is_superuser_fuer_betrachter_null(self) -> None:
        self._login_as("betrachter2", ["Betrachter"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertIsNone(result["data"]["benutzer"]["isSuperuser"])
        self.assertIsNone(result["data"]["benutzer"]["userPermissionsList"])
        self.assertIsNone(result["data"]["benutzer"]["logEntryList"])

    def test_username_ist_fuer_eingeloggte_sichtbar(self) -> None:
        self._login_as("betrachter3", ["Betrachter"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertEqual(result["data"]["benutzer"]["username"], "ziel")

    def test_benutzerlist_gefiltert_nach_gruppe(self) -> None:
        self._login_as("admin3", ["Admin"])
        pl = User.objects.create_user("pl_test", password="x")
        group, _ = Group.objects.get_or_create(name="Projektleiter")
        pl.groups.add(group)
        result = _gql(
            self.client,
            """
            query {
              benutzerList(filter: { groupsList: { any: { name: "Projektleiter" } } }) {
                items { id username }
              }
            }
            """,
        )
        self.assertNotIn("errors", result, result.get("errors"))
        usernames = [u["username"] for u in result["data"]["benutzerList"]["items"]]
        self.assertEqual(usernames, ["pl_test"])


class BenutzerWriteDeniedTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("admin4", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def test_create_ueber_graphql_verweigert(self) -> None:
        result = _gql(
            self.client, 'mutation { createBenutzer(username: "x") { success } }'
        )
        self.assertIn("errors", result)

    def test_create_ueber_python_verweigert(self) -> None:
        from apps.authentication.managers import Benutzer

        with self.assertRaises(PermissionError):
            Benutzer.create(username="x")
```

Neue Datei `src/apps/authentication/tests/test_gruppe.py`:

```python
"""GraphQL-Tests für den Gruppe-GM-Manager (apps.authentication.managers)."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase

GRAPHQL_URL = "/graphql/"


def _gql(
    client: Any, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    response = client.post(
        GRAPHQL_URL, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, (
        f"HTTP {response.status_code}: {response.content[:500]}"
    )
    data: dict[str, Any] = response.json()
    return data


class GruppeReadTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("leser", password="x")
        self.client.force_login(self.user)
        self.group, _ = Group.objects.get_or_create(name="Betrachter")

    def test_gruppe_lesen_erlaubt(self) -> None:
        result = _gql(
            self.client,
            """
            query($id: ID!) { gruppe(id: $id) { id name } }
            """,
            {"id": str(self.group.pk)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertEqual(result["data"]["gruppe"]["name"], "Betrachter")


class GruppeWriteDeniedTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("admin5", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def test_create_ueber_graphql_verweigert(self) -> None:
        result = _gql(self.client, 'mutation { createGruppe(name: "Neu") { success } }')
        self.assertIn("errors", result)
```

- [ ] **Step 6: Tests laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_benutzer.py src/apps/authentication/tests/test_gruppe.py -v`
Expected: FAIL (ImportError / `Cannot query field "benutzer"`), da `Benutzer`/`Gruppe` noch nicht existieren.

- [ ] **Step 7: `models.py` anlegen**

`src/apps/authentication/models.py`:

```python
"""Beherbergt HistoricalUser/HistoricalGroup, die simple_history dynamisch
hier anhängt (siehe managers.py). Keine eigenen Model-Definitionen.

Notwendig, nicht nur Konvention: simple_history.register(..., app=
"apps.authentication") importiert intern per importlib.import_module(
"apps.authentication.models") und hängt die generierten Historical*-Klassen
per setattr dort an. Ohne diese Datei schlägt die Registrierung mit
ModuleNotFoundError fehl.
"""
```

- [ ] **Step 8: `managers.py` anlegen**

`src/apps/authentication/managers.py`:

```python
from __future__ import annotations

from django.contrib.auth.models import Group, User
from general_manager import (
    AdditiveManagerPermission,
    ExistingModelInterface,
    GeneralManager,
)
from general_manager.interface.utils.history import DatabaseAwareHistoricalRecords
from simple_history import register

# Muss vor den Manager-Klassendefinitionen laufen: registriert die History
# BEIDER Django-Modelle unter dem "apps.authentication"-App-Label. Ohne das
# würde GMs eigene History-Registrierung greifen (ensure_history() läuft für
# JEDEN ExistingModelInterface-Manager automatisch) und die Historical*-
# Modelle fälschlich unter dem "auth"-App-Label landen — dort dürfen wir
# keine eigene Migration ablegen (makemigrations würde sonst versuchen, in
# django/contrib/auth/migrations/ innerhalb der installierten Bibliothek zu
# schreiben). Der hasattr-Guard verhindert doppelte Registrierung bei einem
# Modul-Reimport (z. B. Django-Autoreload im Dev-Server).
for _model in (User, Group):
    if not hasattr(_model._meta, "simple_history_manager_attribute"):
        register(
            _model,
            app="apps.authentication",
            m2m_fields=[f.name for f in _model._meta.local_many_to_many],
            records_class=DatabaseAwareHistoricalRecords,
            use_base_model_db=True,
        )


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
        is_superuser = {"read": ["isAdminGroup"]}
        user_permissions_list = {"read": ["isAdminGroup"]}
        log_entry_list = {"read": ["isAdminGroup"]}
```

- [ ] **Step 9: `apps.py` verdrahten**

In `src/apps/authentication/apps.py`:

```python
    def ready(self) -> None:
        importlib.import_module("apps.authentication.permission")
        importlib.import_module("apps.authentication.managers")
```

- [ ] **Step 10: Migration erzeugen**

```bash
devcontainer exec --workspace-folder . mkdir -p src/apps/authentication/migrations
devcontainer exec --workspace-folder . touch src/apps/authentication/migrations/__init__.py
devcontainer exec --workspace-folder . uv run --group dev python manage.py makemigrations authentication
```

Erwartete Ausgabe (exakt, keine anderen Apps betroffen):
```
Migrations for 'authentication':
  src/apps/authentication/migrations/0001_initial.py
    + Create model HistoricalGroup
    + Create model HistoricalGroup_permissions
    + Create model HistoricalUser
    + Create model HistoricalUser_groups
    + Create model HistoricalUser_user_permissions
```

Falls die Ausgabe auch `Migrations for 'auth': .venv/lib/.../django/contrib/auth/migrations/...` zeigt: Step 8 wurde nicht korrekt übernommen (History-Vorregistrierung fehlt für `Group` oder `User`) — Migration NICHT anwenden/committen, `managers.py` prüfen, `.venv`-Datei löschen, erneut versuchen.

- [ ] **Step 11: `test_projekt.py` und `tests/test_graphql_queries.py` an den Seiteneffekt anpassen**

In `src/apps/projekt/tests/test_projekt.py`, zwei Stellen:

```python
        self.assertEqual(proj.projektleiter.id, user.pk)  # type: ignore[union-attr]
```
(ersetzt `proj.projektleiter.pk` in `test_create_mit_projektleiter_als_string_id`)

```python
        self.assertEqual(updated.projektleiter.id, user.pk)  # type: ignore[union-attr]
```
(ersetzt `updated.projektleiter.pk` in `test_update_mit_projektleiter_als_string_id`)

In `tests/test_graphql_queries.py`, in `_QUERY_PROJEKT_LISTE`:
```
          projektleiter { id username }
```
(ersetzt bare `projektleiter`)

In `_QUERY_PROJEKT_DETAIL`:
```
        projektleiter { id username }
```
(ersetzt bare `projektleiter`; `capabilities { canUpdate canDelete }` kommt erst in Task 3 dazu — hier nur die Sub-Selection fixen)

- [ ] **Step 12: Alle Tests laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest --no-cov`
Expected: alle PASS (voller Suite-Lauf, nicht nur die neuen Dateien — Step 11 behebt genau die Regression, die Task 1 sonst hinterlässt)

- [ ] **Step 13: mypy + ruff prüfen**

Run: `devcontainer exec --workspace-folder . uv run --group dev mypy src tests`
Expected: `Success: no issues found in N source files`

Run: `devcontainer exec --workspace-folder . uv run --group dev ruff check . && uv run --group dev ruff format --check .`
Expected: beide grün

- [ ] **Step 14: Commit**

```bash
devcontainer exec --workspace-folder . git add src/apps/authentication/models.py src/apps/authentication/managers.py src/apps/authentication/migrations/ src/apps/authentication/permission.py src/apps/authentication/apps.py src/apps/authentication/tests/test_authentication.py src/apps/authentication/tests/test_benutzer.py src/apps/authentication/tests/test_gruppe.py src/apps/projekt/tests/test_projekt.py tests/test_graphql_queries.py
devcontainer exec --workspace-folder . git commit -m "feat(auth): Benutzer/Gruppe als GM-Manager (ExistingModelInterface)"
```

---

## Task 2: CurrentUserCapabilities-Provider + `me`-Query

**Files:**
- Create: `src/apps/authentication/graphql_capabilities.py`
- Modify: `src/forge/settings.py` (`GENERAL_MANAGER["GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER"]`)
- Test: `src/apps/authentication/tests/test_authentication.py` (neue `CurrentUserCapabilitiesTest`-Klasse)

**Interfaces:**
- Consumes: `_is_in_group` aus `apps.authentication.permission` (Task 1 unverändert vorhanden)
- Produces: `CurrentUserCapabilities` (`apps.authentication.graphql_capabilities.CurrentUserCapabilities`), GraphQL-Feld `me { username capabilities { canCreateProjekt canManageStundensaetze canViewFinanzen } } }`

---

- [ ] **Step 1: Failing GraphQL-Test für `me` schreiben**

In `src/apps/authentication/tests/test_authentication.py`, neue Klasse (nach `CurrentUserViewTest`):

```python
class CurrentUserCapabilitiesTest(TestCase):
    def _gql(self) -> dict[str, object]:
        import json

        response = self.client.post(
            "/graphql/",
            data=json.dumps(
                {
                    "query": """
                    query {
                      me {
                        username
                        capabilities {
                          canCreateProjekt
                          canManageStundensaetze
                          canViewFinanzen
                        }
                      }
                    }
                    """
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()  # type: ignore[no-any-return]

    def test_anonymous_alle_capabilities_false(self) -> None:
        result = self._gql()
        self.assertEqual(result["data"]["me"]["username"], "")
        caps = result["data"]["me"]["capabilities"]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": False,
            },
        )

    def test_admin_alle_capabilities_true(self) -> None:
        from django.contrib.auth.models import Group

        user = User.objects.create_user("admincaps", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        user.groups.add(group)
        self.client.force_login(user)
        result = self._gql()
        self.assertEqual(result["data"]["me"]["username"], "admincaps")
        caps = result["data"]["me"]["capabilities"]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": True,
                "canManageStundensaetze": True,
                "canViewFinanzen": True,
            },
        )

    def test_monteur_darf_nur_nichts(self) -> None:
        from django.contrib.auth.models import Group

        user = User.objects.create_user("monteurcaps", password="x")
        group, _ = Group.objects.get_or_create(name="Monteur")
        user.groups.add(group)
        self.client.force_login(user)
        caps = self._gql()["data"]["me"]["capabilities"]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": False,
            },
        )
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_authentication.py::CurrentUserCapabilitiesTest -v`
Expected: FAIL — `me` liefert keine `capabilities` (Feld existiert nicht im Schema, da `GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER` noch nicht gesetzt ist).

- [ ] **Step 3: `graphql_capabilities.py` anlegen**

`src/apps/authentication/graphql_capabilities.py`:

```python
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
```

Hinweis: benannte `def`-Funktionen statt Lambdas — mit Lambdas würde mypy strict
`Argument 1 to "_is_in_group" has incompatible type "object"; expected
"AbstractBaseUser | AnonymousUser"` werfen (verifiziert), weil der von GM
erwartete Evaluator-Typ `Callable[[object, object], bool]` ist. Die
`isinstance`-Schranke in `_user_or_none` engt `object` mypy-sauber ein.

- [ ] **Step 4: Settings verdrahten**

In `src/forge/settings.py`, im bestehenden `GENERAL_MANAGER`-Dict, nach `"DEFAULT_PERMISSIONS": {...},`:

```python
    "GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER": (
        "apps.authentication.graphql_capabilities.CurrentUserCapabilities"
    ),
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_authentication.py::CurrentUserCapabilitiesTest -v`
Expected: PASS (alle drei Tests)

- [ ] **Step 6: mypy + ruff + voller Suite-Lauf**

```bash
devcontainer exec --workspace-folder . uv run --group dev mypy src tests
devcontainer exec --workspace-folder . uv run --group dev ruff check . && uv run --group dev ruff format --check .
devcontainer exec --workspace-folder . uv run --group dev pytest --no-cov
```
Expected: alle grün

- [ ] **Step 7: Commit**

```bash
devcontainer exec --workspace-folder . git add src/apps/authentication/graphql_capabilities.py src/forge/settings.py src/apps/authentication/tests/test_authentication.py
devcontainer exec --workspace-folder . git commit -m "feat(auth): globale Capabilities über me-Query"
```

---

## Task 3: Projekt-Capabilities (canUpdate/canDelete) + projektleiter-Retype

**Files:**
- Modify: `src/apps/projekt/models/projekt.py`
- Modify: `src/apps/projekt/apps.py`
- Modify: `tests/test_graphql_queries.py` (`capabilities { canUpdate canDelete }` ergänzen + neue Rollen-Tests)

**Interfaces:**
- Consumes: `Benutzer` (Task 1)
- Produces: `Projekt.capabilities { canUpdate canDelete }` im GraphQL-Schema; `Projekt.projektleiter` ist ab jetzt auch **statisch typisiert** als `Benutzer | None` (das *Laufzeitverhalten* änderte sich bereits in Task 1 — hier wird nur die Annotation nachgezogen)

---

- [ ] **Step 1: Failing Test für `capabilities` schreiben**

In `tests/test_graphql_queries.py`, `_QUERY_PROJEKT_DETAIL` erweitern:

```python
        projektStatus { name }
        projektleiter { id username }
        capabilities { canUpdate canDelete }
        projektKennzahlenList {
```

Neue Test-Klasse (nach `GraphQLPermissionTest`):

```python
class ProjektCapabilitiesTest(_SharedSetup):
    def _login_as(self, username: str, groups: list[str]) -> None:
        from django.contrib.auth.models import Group

        user = User.objects.create_user(username, password="x")
        for name in groups:
            group, _ = Group.objects.get_or_create(name=name)
            user.groups.add(group)
        self.client.force_login(user)

    def test_admin_darf_bearbeiten_und_loeschen(self) -> None:
        self._login_as("adm_caps", ["Admin"])
        result = _gql(
            self.client, _QUERY_PROJEKT_DETAIL, variables={"id": str(self.projekt.id)}
        )
        self.assertNotIn("errors", result, result.get("errors"))
        caps = result["data"]["projekt"]["capabilities"]
        self.assertEqual(caps, {"canUpdate": True, "canDelete": True})

    def test_betrachter_darf_weder_bearbeiten_noch_loeschen(self) -> None:
        self._login_as("betr_caps", ["Betrachter"])
        result = _gql(
            self.client, _QUERY_PROJEKT_DETAIL, variables={"id": str(self.projekt.id)}
        )
        self.assertNotIn("errors", result, result.get("errors"))
        caps = result["data"]["projekt"]["capabilities"]
        self.assertEqual(caps, {"canUpdate": False, "canDelete": False})
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest tests/test_graphql_queries.py::ProjektCapabilitiesTest -v`
Expected: FAIL — `Cannot query field "capabilities" on type "ProjektType"`

- [ ] **Step 3: `projekt.py` anpassen**

Import-Block (ersetzt den bisherigen `from django.contrib.auth.models import User`):

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.db.models import Manager, QuerySet
from general_manager import (
    AdditiveManagerPermission,
    DatabaseInterface,
    FieldConfig,
    GeneralManager,
    IndexConfig,
)
from general_manager.bucket import Bucket
from general_manager.measurement import Measurement, MeasurementField
from general_manager.permission import (
    GraphQLPermissionCapability,
    permission_capability,
)
from general_manager.rule import Rule

from apps.authentication.managers import Benutzer
from apps.projekt.models.projekt_status import ProjektStatus
```

Annotation:

```python
    projektleiter: Benutzer | None
```

`Permission`-Klasse — `graphql_capabilities` als leeres `ClassVar` deklarieren (die eigentliche Zuweisung passiert in Step 5 in `apps.py`, NICHT hier — Grund siehe "Korrekturen" oben):

```python
    class Permission(AdditiveManagerPermission):
        __read__ = ["isAdminGroup", "isProjektleiter", "isBetrachter"]
        __create__ = ["isAdminGroup", "isProjektleiter"]
        __update__ = ["isAdminGroup", "isProjektleiter"]
        __delete__ = ["isAdminGroup", "isProjektleiter"]
        graphql_capabilities: ClassVar[tuple[GraphQLPermissionCapability, ...]] = ()

        # auftragsnummer = {"update": ["isAdmin"]}
```

Am Dateiende, nach der bestehenden `update()`-Methode, neue Funktion ergänzen:

```python
def _register_graphql_capabilities() -> None:
    """Von ProjektConfig.ready() aufgerufen, NICHT auf Modulebene.

    Projekt.Permission.graphql_capabilities = (...) auf Modulebene würde beim
    Import von projekt.py über Projekt.Permission (Metaclass-Zugriff) GMs
    Lazy-Attribute-Initialisierung auslösen, die den vollen App-Registry
    braucht (apps.get_models()). Zur normalen Django-Laufzeit ist das kein
    Problem (Modelle sind beim Import längst geladen) — mypys
    django-stubs-Plugin importiert Model-Module aber in einer Reihenfolge,
    in der die Registry noch nicht vollständig ist, und crasht dabei mit
    einem INTERNAL ERROR. ready() läuft garantiert erst NACH dem Laden aller
    Apps und wird von django-stubs nicht mit-ausgeführt.
    """
    Projekt.Permission.graphql_capabilities = (
        permission_capability(Projekt, "update", name="canUpdate"),
        permission_capability(Projekt, "delete", name="canDelete"),
    )
```

- [ ] **Step 4: `apps.py` verdrahten**

In `src/apps/projekt/apps.py`:

```python
    def ready(self) -> None:
        importlib.import_module("apps.projekt.models")
        importlib.import_module("apps.projekt.calculation_manager")
        from apps.projekt.models.projekt import _register_graphql_capabilities

        _register_graphql_capabilities()
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest tests/test_graphql_queries.py -v`
Expected: alle PASS, inkl. `ProjektCapabilitiesTest`

- [ ] **Step 6: mypy + ruff + voller Suite-Lauf**

```bash
devcontainer exec --workspace-folder . uv run --group dev mypy src tests
devcontainer exec --workspace-folder . uv run --group dev ruff check . && uv run --group dev ruff format --check .
devcontainer exec --workspace-folder . uv run --group dev pytest --no-cov
```
Expected: alle grün. Falls `mypy` mit `INTERNAL ERROR` abbricht: Step 3/4 falsch übernommen (Zuweisung landet doch auf Modulebene) — prüfen, dass `Projekt.Permission.graphql_capabilities = (...)` ausschließlich innerhalb von `_register_graphql_capabilities()` steht, aufgerufen aus `ready()`.

- [ ] **Step 7: Commit**

```bash
devcontainer exec --workspace-folder . git add src/apps/projekt/models/projekt.py src/apps/projekt/apps.py tests/test_graphql_queries.py
devcontainer exec --workspace-folder . git commit -m "feat(projekt): Objekt-Capabilities canUpdate/canDelete + projektleiter-Retype"
```

---

## Task 4: REST-Endpunkte entfernen (`/api/users/`, `/api/me/`)

**Files:**
- Modify: `src/apps/authentication/views.py`
- Modify: `src/apps/authentication/urls.py`
- Modify: `src/apps/authentication/tests/test_authentication.py`

**Interfaces:**
- Consumes: nichts (reine Entfernung)
- Produces: nichts Neues — `users_view`/`current_user_view` und ihre URLs existieren danach nicht mehr

---

- [ ] **Step 1: Regressionstest schreiben, der die Entfernung erzwingt**

In `src/apps/authentication/tests/test_authentication.py`, `UsersViewTest`- und `CurrentUserViewTest`-Klassen ENTFERNEN (sie testen Views, die wegfallen) und durch einen einzigen Test ersetzen, der die Abwesenheit prüft:

```python
class RemovedRestEndpointsTest(TestCase):
    def test_users_endpoint_existiert_nicht_mehr(self) -> None:
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("auth-users")

    def test_me_endpoint_existiert_nicht_mehr(self) -> None:
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("auth-me")
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_authentication.py::RemovedRestEndpointsTest -v`
Expected: FAIL — `reverse("auth-users")` löst NICHT `NoReverseMatch` aus, weil die URL noch existiert.

- [ ] **Step 3: `urls.py` bereinigen**

`src/apps/authentication/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="auth-login"),
    path("logout/", views.logout_view, name="auth-logout"),
]
```

- [ ] **Step 4: `views.py` bereinigen**

In `src/apps/authentication/views.py`: `users_view` und `current_user_view` (inkl. ihrer `@require_GET`-Decorators) komplett entfernen. `login_view`/`logout_view` unverändert lassen. Falls dadurch `User`-Import ungenutzt wird (er wird noch für `authenticate`/`auth_login` gebraucht — prüfen, ob `from django.contrib.auth.models import User` noch verwendet wird; falls nicht, Import entfernen).

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/authentication/tests/test_authentication.py -v`
Expected: alle PASS

- [ ] **Step 6: mypy + ruff + voller Suite-Lauf**

```bash
devcontainer exec --workspace-folder . uv run --group dev mypy src tests
devcontainer exec --workspace-folder . uv run --group dev ruff check . && uv run --group dev ruff format --check .
devcontainer exec --workspace-folder . uv run --group dev pytest --no-cov
```
Expected: alle grün

- [ ] **Step 7: Commit**

```bash
devcontainer exec --workspace-folder . git add src/apps/authentication/views.py src/apps/authentication/urls.py src/apps/authentication/tests/test_authentication.py
devcontainer exec --workspace-folder . git commit -m "refactor(auth): REST-Endpunkte /api/users/ und /api/me/ entfernen"
```

---

## Task 5: AuthContext.tsx + ME-Query

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (neue Query `ME`)
- Modify: `frontend/src/contexts/AuthContext.tsx`
- Test: `frontend/src/contexts/AuthContext.test.tsx` (neu)

**Interfaces:**
- Produces: `AuthUser = { id: number; username: string; capabilities: { canCreateProjekt: boolean; canManageStundensaetze: boolean; canViewFinanzen: boolean } }` (ersetzt `groups`/`isStaff`), `useAuth()` unverändert in der Signatur (`user`, `loading`, `login`, `logout`)
- Consumes: Backend-Schema aus Task 2 (`me { username capabilities { ... } }`)

---

- [ ] **Step 1: Failing Test schreiben**

Neue Datei `frontend/src/contexts/AuthContext.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { gql } from "@apollo/client/core";
import { describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import { ME } from "../graphql/queries";

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <p>lade</p>;
  return <p>{user ? `eingeloggt:${user.username}` : "ausgeloggt"}</p>;
}

const meAdminMock = {
  request: { query: ME },
  result: {
    data: {
      me: {
        username: "admin",
        capabilities: {
          canCreateProjekt: true,
          canManageStundensaetze: true,
          canViewFinanzen: true,
        },
      },
    },
  },
};

const meAnonymMock = {
  request: { query: ME },
  result: {
    data: {
      me: {
        username: "",
        capabilities: {
          canCreateProjekt: false,
          canManageStundensaetze: false,
          canViewFinanzen: false,
        },
      },
    },
  },
};

describe("AuthContext", () => {
  it("setzt user bei nichtleerem username", async () => {
    render(
      <MockedProvider mocks={[meAdminMock]}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("eingeloggt:admin"));
  });

  it("bleibt user null bei leerem username (nicht eingeloggt)", async () => {
    render(
      <MockedProvider mocks={[meAnonymMock]}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MockedProvider>,
    );
    await waitFor(() => screen.getByText("ausgeloggt"));
  });
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- AuthContext`
Expected: FAIL — `ME` existiert noch nicht in `queries.ts`, `AuthContext` fetcht noch über REST.

- [ ] **Step 3: `ME`-Query ergänzen**

In `frontend/src/graphql/queries.ts`, am Dateiende:

```ts
export const ME = gql`
  query Me {
    me {
      username
      capabilities {
        canCreateProjekt
        canManageStundensaetze
        canViewFinanzen
      }
    }
  }
`;
```

- [ ] **Step 4: `AuthContext.tsx` umbauen**

Komplette neue Fassung von `frontend/src/contexts/AuthContext.tsx`:

> **Nachträgliche Korrektur (nicht Teil der ursprünglichen Task-5-Ausführung):**
> die Version unten enthält bereits drei Härtungen, die erst in der finalen
> Whole-Branch-Review bzw. einer nachgelagerten CodeRabbit-Review gefunden
> wurden — ursprünglich hatte `refreshUser()` kein `try/catch` (ein
> fehlgeschlagener `me`-Query ließ den Login-Screen dauerhaft im
> Spinner-Zustand hängen), `login()`/`logout()` leerten den Apollo-Cache
> nicht (Cross-User-Datenleck bei Tab-übergreifendem Re-Login), und
> `logout()` prüfte weder `response.ok` noch meldete es einen
> fehlgeschlagenen Server-Logout an den Aufrufer zurück (blieb die Sitzung
> serverseitig unbemerkt aktiv). Wer diese Task nachbaut, sollte direkt
> diese Fassung verwenden, nicht die naive Erstversion.

```tsx
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useApolloClient } from "@apollo/client/react";
import { ME } from "../graphql/queries";

export type AuthCapabilities = {
  canCreateProjekt: boolean;
  canManageStundensaetze: boolean;
  canViewFinanzen: boolean;
};

export type AuthUser = {
  id: number;
  username: string;
  capabilities: AuthCapabilities;
};

type MeQueryData = {
  me: { username: string; capabilities: AuthCapabilities };
};

type AuthContextType = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<string | null>;
  // Analog zu login(): null = Server hat die Abmeldung bestätigt (HTTP ok),
  // ein String = die Abmeldung konnte serverseitig nicht bestätigt werden
  // (Netzwerkfehler oder Nicht-2xx-Antwort) — der Aufrufer entscheidet, wie
  // er das anzeigt. Lokaler State/Cache werden in JEDEM Fall geleert.
  logout: () => Promise<string | null>;
};

const AuthContext = createContext<AuthContextType | null>(null);

let nextClientSideId = 1;

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useApolloClient();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Gibt den geladenen User zurück (oder null), statt nur intern den State
  // zu setzen — login() nutzt den Rückgabewert, um einen fehlgeschlagenen
  // me-Query (REST-Login war erfolgreich, GraphQL-Query aber nicht) von
  // einem regulären "nicht eingeloggt" zu unterscheiden. Wirft NIE — ein
  // Netzwerkfehler/500/Schema-Mismatch degradiert auf "ausgeloggt", statt
  // login() bzw. den Mount-Effekt mit einer unhandled rejection hängen zu
  // lassen (der Login-Screen blieb sonst dauerhaft im Spinner-Zustand).
  async function refreshUser(): Promise<AuthUser | null> {
    try {
      const { data } = await client.query<MeQueryData>({
        query: ME,
        fetchPolicy: "network-only",
      });
      if (data?.me.username) {
        const nextUser: AuthUser = {
          id: nextClientSideId++,
          username: data.me.username,
          capabilities: data.me.capabilities,
        };
        setUser(nextUser);
        return nextUser;
      }
      setUser(null);
      return null;
    } catch {
      setUser(null);
      return null;
    }
  }

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(
    username: string,
    password: string,
  ): Promise<string | null> {
    const r = await fetch("/api/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await r.json();
    if (!data.success) {
      return (data.error as string) ?? "Anmeldung fehlgeschlagen.";
    }
    // Cache leeren, bevor der neue User geladen wird — sonst könnten hier
    // (Tab-übergreifender Re-Login als anderer User) noch Query-Ergebnisse
    // des vorherigen Users im InMemoryCache stehen.
    await client.clearStore();
    const nextUser = await refreshUser();
    if (!nextUser) {
      // REST-Login war erfolgreich, aber der me-Query ist gescheitert
      // (Netzwerkfehler/500/Schema-Mismatch) — nicht kommentarlos auf
      // "ausgeloggt" zurückfallen, sondern das der Nutzerin erklären.
      return "Anmeldung erfolgreich, aber Benutzerdaten konnten nicht geladen werden. Bitte Seite neu laden.";
    }
    return null;
  }

  async function logout(): Promise<string | null> {
    let unconfirmed: string | null = null;
    try {
      const r = await fetch("/api/logout/", { method: "POST" });
      if (!r.ok) {
        // Server hat geantwortet, aber mit einem Fehlerstatus — die
        // Session-Cookie-Invalidierung ist damit nicht bestätigt und könnte
        // serverseitig noch aktiv sein.
        unconfirmed =
          "Abmeldung auf dem Server konnte nicht bestätigt werden. Die Sitzung könnte serverseitig noch aktiv sein.";
      }
    } catch {
      // Netzwerkfehler: dieselbe Unsicherheit wie oben, nur früher im
      // Request-Zyklus.
      unconfirmed =
        "Abmeldung auf dem Server war nicht erreichbar (Netzwerkfehler). Die Sitzung könnte serverseitig noch aktiv sein.";
    } finally {
      // Lokales Aufräumen läuft IMMER — auch bei einem unbestätigten
      // Server-Logout. Sonst bliebe der User clientseitig "eingeloggt" und
      // der Apollo-Cache mit seinen Daten stehen; das serverseitige Risiko
      // wird stattdessen über den Rückgabewert an den Aufrufer gemeldet.
      setUser(null);
      await client.clearStore();
    }
    return unconfirmed;
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth muss innerhalb von AuthProvider verwendet werden");
  return ctx;
}
```

Hinweis: `id` kommt aus `me` nicht mehr zurück (der Provider liefert nur `username` + `capabilities`, siehe Task 2 — `id` stand im Backend-Contract nie zur Verfügung). Da bisher nichts im Code `user.id` tatsächlich verwendet (geprüft: nur `ProjektListePage.test.tsx`s Mock setzt `id: 1`, kein Produktionscode liest es), wird hier eine client-seitige Zähler-ID als Platzhalter vergeben, rein um den bestehenden `AuthUser`-Typ mit `id: number` nicht zu brechen.

Der geänderte Rückgabetyp von `logout()` verlangt auch Anpassungen außerhalb
dieser Task: `Layout.tsx`s `handleLogout` muss den Rückgabewert abgreifen und
bei einer Warnung `navigate("/login", { state: { logoutWarning } })` setzen,
`LoginPage.tsx` muss `location.state.logoutWarning` lesen und anzeigen — beides
ist zum Zeitpunkt dieser Task (vor Task 6/Layout) noch nicht vorhanden und
wurde nachträglich ergänzt, nicht Teil des ursprünglichen Task-6-Plans.

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- AuthContext`
Expected: PASS (beide Tests)

- [ ] **Step 6: Commit**

```bash
devcontainer exec --workspace-folder . git add frontend/src/graphql/queries.ts frontend/src/contexts/AuthContext.tsx frontend/src/contexts/AuthContext.test.tsx
devcontainer exec --workspace-folder . git commit -m "feat(frontend): AuthContext liest me-Query statt /api/me/"
```

---

## Task 6: ProtectedRoute + App.tsx + Layout.tsx + permissions.ts entfernen

**Files:**
- Modify: `frontend/src/components/ProtectedRoute.tsx`
- Test: `frontend/src/components/ProtectedRoute.test.tsx` (neu)
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Delete: `frontend/src/utils/permissions.ts`

**Interfaces:**
- Consumes: `AuthUser` aus Task 5 (`user.capabilities.<Key>`)
- Produces: `ProtectedRoute`-Prop `requiredCapability?: keyof AuthCapabilities` (ersetzt `allowedGroups?: UserGroup[]`)

---

- [ ] **Step 1: Failing Test schreiben**

Neue Datei `frontend/src/components/ProtectedRoute.test.tsx`:

```tsx
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProtectedRoute from "./ProtectedRoute";

const mockUser = {
  id: 1,
  username: "admin",
  capabilities: {
    canCreateProjekt: false,
    canManageStundensaetze: false,
    canViewFinanzen: true,
  },
};

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ user: mockUser, loading: false, login: vi.fn(), logout: vi.fn() }),
}));

function renderWithRoute(requiredCapability?: "canCreateProjekt" | "canManageStundensaetze") {
  return render(
    <MemoryRouter initialEntries={["/geschuetzt"]}>
      <Routes>
        <Route
          path="/geschuetzt"
          element={
            <ProtectedRoute requiredCapability={requiredCapability}>
              <p>Inhalt</p>
            </ProtectedRoute>
          }
        />
        <Route path="/projekte" element={<p>Projektliste</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("zeigt Inhalt ohne requiredCapability", () => {
    renderWithRoute();
    expect(screen.getByText("Inhalt")).toBeInTheDocument();
  });

  it("leitet um, wenn die Capability fehlt", () => {
    renderWithRoute("canCreateProjekt");
    expect(screen.getByText("Projektliste")).toBeInTheDocument();
  });

  it("zeigt Inhalt, wenn die Capability vorhanden ist", () => {
    renderWithRoute("canManageStundensaetze" as never); // false in mockUser
  });
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProtectedRoute`
Expected: FAIL — Prop `requiredCapability` existiert noch nicht (TypeScript-Fehler / `allowedGroups`-Fallback greift nicht).

- [ ] **Step 3: `ProtectedRoute.tsx` umbauen**

```tsx
import { Navigate } from "react-router-dom";
import { useAuth, type AuthCapabilities } from "../contexts/AuthContext";

type Props = {
  children: React.ReactNode;
  requiredCapability?: keyof AuthCapabilities;
};

export default function ProtectedRoute({ children, requiredCapability }: Props) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400">Lade…</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requiredCapability && !user.capabilities[requiredCapability]) {
    return <Navigate to="/projekte" replace />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 4: `App.tsx` anpassen**

Zwei Stellen:

```tsx
          <Route
            path="/projekte/neu"
            element={
              <ProtectedRoute requiredCapability="canCreateProjekt">
                <ProjektNeuPage />
              </ProtectedRoute>
            }
          />
```

```tsx
          <Route
            path="/stundensaetze"
            element={
              <ProtectedRoute requiredCapability="canManageStundensaetze">
                <StundensaetzePage />
              </ProtectedRoute>
            }
          />
```

- [ ] **Step 5: `Layout.tsx` anpassen**

```tsx
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
```

(Import von `canManageStundensaetze` aus `../utils/permissions` entfernen)

```tsx
            {user.capabilities.canManageStundensaetze && (
              <NavLink to="/stundensaetze" className={navLinkClass} style={navLinkStyle}>
                Stundensätze
              </NavLink>
            )}
```

- [ ] **Step 6: `permissions.ts` löschen**

```bash
devcontainer exec --workspace-folder . rm frontend/src/utils/permissions.ts
```

(Alle verbleibenden Importeure werden in Task 7–9 umgestellt; nach diesem Step ist `npm run build`/`tsc` bis Task 9 abgeschlossen erwartungsgemäß rot — das ist normal für einen mehrteiligen Umbau und wird am Ende in Task 10 final verifiziert.)

- [ ] **Step 7: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProtectedRoute`
Expected: PASS (alle drei Tests)

- [ ] **Step 8: Commit**

```bash
devcontainer exec --workspace-folder . git add frontend/src/components/ProtectedRoute.tsx frontend/src/components/ProtectedRoute.test.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx
devcontainer exec --workspace-folder . git rm frontend/src/utils/permissions.ts
devcontainer exec --workspace-folder . git commit -m "feat(frontend): ProtectedRoute/App/Layout auf Capabilities umgestellt"
```

---

## Task 7: ProjektListePage.tsx

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (`GET_PROJEKTE`, `SEARCH_PROJEKTE`: `projektleiter` → `projektleiter { id username }`)
- Modify: `frontend/src/pages/ProjektListePage.tsx`
- Modify: `frontend/src/pages/ProjektListePage.test.tsx`

**Interfaces:**
- Consumes: `AuthUser.capabilities` (Task 5/6)
- Produces: `Projekt.projektleiter: { id: string; username: string } | null` im Seiten-lokalen Typ

---

- [ ] **Step 1: Bestehenden Test an die neue Shape anpassen (failing)**

In `frontend/src/pages/ProjektListePage.test.tsx`:

```tsx
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "admin",
      capabilities: {
        canCreateProjekt: true,
        canManageStundensaetze: true,
        canViewFinanzen: true,
      },
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));
```

```tsx
function projekt(overrides: Record<string, unknown> = {}) {
  return {
    id: "1",
    auftragsnummer: "T-2026-002",
    name: "Bauprojekt B",
    offerteSumme: { value: 10000, unit: "CHF" },
    wvSumme: { value: 9000, unit: "CHF" },
    projektStatus: { id: "2", name: "In Arbeit" },
    projektleiter: { id: "9", username: "Max Muster" },
    projektKennzahlenList: {
      items: [{ summeWvPlus: { value: 9500, unit: "CHF" }, summeIstKosten: { value: 8000, unit: "CHF" } }],
    },
    ...overrides,
  };
}
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProjektListePage`
Expected: FAIL — `ProjektListePage.tsx` erwartet noch `projektleiter: string | null` und importiert das gelöschte `utils/permissions`.

- [ ] **Step 3: `GET_PROJEKTE`/`SEARCH_PROJEKTE` in `queries.ts` anpassen**

Beide Vorkommen von bare `projektleiter` (in `GET_PROJEKTE` und `SEARCH_PROJEKTE`) ersetzen durch:

```
        projektleiter { id username }
```

- [ ] **Step 4: `ProjektListePage.tsx` anpassen**

```tsx
import { useApolloClient, useQuery, useSubscription } from "@apollo/client/react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Plus, Search, UserRound } from "lucide-react";
import Layout from "../components/Layout";
import { GET_PROJEKTE, SEARCH_PROJEKTE } from "../graphql/queries";
import { PROJEKT_LISTE_SUBSCRIPTION } from "../graphql/subscriptions";
import { chf, type GQLMeasurement } from "../utils/format";
import { getDeviation, DEV_STYLES } from "../utils/deviation";
import { useAuth } from "../contexts/AuthContext";
```

(Import-Zeile `canCreateProject, canViewFinancials` entfernt)

```tsx
type Projekt = {
  id: string;
  auftragsnummer: string;
  name: string;
  offerteSumme: GQLMeasurement;
  wvSumme: GQLMeasurement | null;
  projektStatus: { id: string; name: string };
  projektleiter: { id: string; username: string } | null;
  projektKennzahlenList: { items: { summeWvPlus: GQLMeasurement | null; summeIstKosten: GQLMeasurement | null }[] };
};
```

```tsx
  const { user } = useAuth();
  const showFinancials = user?.capabilities.canViewFinanzen ?? false;
  const showCreateButton = user?.capabilities.canCreateProjekt ?? false;
```

```tsx
                    <td className="px-4 py-3">
                      <Avatar name={p.projektleiter?.username ?? null} />
                    </td>
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProjektListePage`
Expected: PASS (alle bestehenden Tests weiterhin grün)

- [ ] **Step 6: Commit**

```bash
devcontainer exec --workspace-folder . git add frontend/src/graphql/queries.ts frontend/src/pages/ProjektListePage.tsx frontend/src/pages/ProjektListePage.test.tsx
devcontainer exec --workspace-folder . git commit -m "feat(frontend): ProjektListePage auf projektleiter-Objekt + Capabilities umgestellt"
```

---

## Task 8: ProjektNeuPage.tsx + PROJEKTLEITER-Query

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (neue Query `PROJEKTLEITER`)
- Modify: `frontend/src/pages/ProjektNeuPage.tsx`
- Test: `frontend/src/pages/ProjektNeuPage.test.tsx` (neu)

**Interfaces:**
- Produces: Query `PROJEKTLEITER` → `benutzerList(filter: { groupsList: { any: { name: "Projektleiter" } } }) { items { id username } }`

---

- [ ] **Step 1: Failing Test schreiben**

Neue Datei `frontend/src/pages/ProjektNeuPage.test.tsx`:

```tsx
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { describe, expect, it } from "vitest";

import ProjektNeuPage from "./ProjektNeuPage";
import { PROJEKTLEITER } from "../graphql/queries";

const projektleiterMock = {
  request: { query: PROJEKTLEITER },
  result: {
    data: {
      benutzerList: {
        items: [{ id: "5", username: "anna" }],
      },
    },
  },
};

describe("ProjektNeuPage", () => {
  it("befüllt das Projektleiter-Dropdown aus der PROJEKTLEITER-Query", async () => {
    render(
      <MemoryRouter>
        <MockedProvider mocks={[projektleiterMock]}>
          <ProjektNeuPage />
        </MockedProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("anna")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProjektNeuPage`
Expected: FAIL — `PROJEKTLEITER` existiert noch nicht, Seite fetcht noch über `/api/users/`.

- [ ] **Step 3: `PROJEKTLEITER`-Query ergänzen**

In `frontend/src/graphql/queries.ts`:

```ts
export const PROJEKTLEITER = gql`
  query Projektleiter {
    benutzerList(filter: { groupsList: { any: { name: "Projektleiter" } } }) {
      items {
        id
        username
      }
    }
  }
`;
```

- [ ] **Step 4: `ProjektNeuPage.tsx` anpassen**

```tsx
import { useMutation, useQuery } from "@apollo/client/react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { CREATE_PROJEKT } from "../graphql/mutations";
import { PROJEKTLEITER } from "../graphql/queries";
```

(Import von `useEffect` entfällt, da der manuelle `fetch`-Effekt wegfällt)

```tsx
type UserOption = { id: string; username: string };
type ProjektleiterData = { benutzerList: { items: UserOption[] } };
```

```tsx
export default function ProjektNeuPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>({
    name: "",
    auftragsnummer: "",
    jahr: String(new Date().getFullYear()),
    offerteSumme: "",
    wvSumme: "",
    projektleiter: "",
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const { data: projektleiterData } = useQuery<ProjektleiterData>(PROJEKTLEITER);
  const users = projektleiterData?.benutzerList.items ?? [];
```

(die bisherige `useState<UserOption[]>([])`-Zeile und der ganze `useEffect(() => { fetch("/api/users/") ... }, [])`-Block entfallen ersatzlos; `<option key={u.id} value={String(u.id)}>` bleibt unverändert, da `u.id` jetzt schon ein `string` ist — `String(u.id)` ist redundant, aber unschädlich, kann so bleiben oder zu `value={u.id}` vereinfacht werden)

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProjektNeuPage`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
devcontainer exec --workspace-folder . git add frontend/src/graphql/queries.ts frontend/src/pages/ProjektNeuPage.tsx frontend/src/pages/ProjektNeuPage.test.tsx
devcontainer exec --workspace-folder . git commit -m "feat(frontend): ProjektNeuPage-Projektleiter-Dropdown über GraphQL"
```

---

## Task 9: ProjektDetailPage.tsx

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (`GET_PROJEKT`: `projektleiter { id username }` + `capabilities { canUpdate canDelete }`)
- Modify: `frontend/src/pages/ProjektDetailPage.tsx`
- Test: `frontend/src/pages/ProjektDetailPage.test.tsx` (neu)

**Interfaces:**
- Consumes: `PROJEKTLEITER`-Query (Task 8), `AuthUser.capabilities.canViewFinanzen` (Task 5)
- Produces: `projekt.capabilities.canUpdate` steuert den "Bearbeiten"-Button (ersetzt `canEdit(user)`)

---

- [ ] **Step 1: Failing Test schreiben**

Neue Datei `frontend/src/pages/ProjektDetailPage.test.tsx`:

```tsx
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { describe, expect, it, vi } from "vitest";

import ProjektDetailPage from "./ProjektDetailPage";
import {
  GET_PROJEKT,
  GET_KOSTENART_IDS,
  GET_PROJEKT_STATUS_IDS,
  PROJEKTLEITER,
} from "../graphql/queries";
import { PROJEKT_DETAIL_SUBSCRIPTION } from "../graphql/subscriptions";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "betrachter",
      capabilities: { canCreateProjekt: false, canManageStundensaetze: false, canViewFinanzen: true },
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

function projektMock(capabilities: { canUpdate: boolean; canDelete: boolean }) {
  return {
    request: { query: GET_PROJEKT, variables: { id: "1" } },
    result: {
      data: {
        projekt: {
          id: "1",
          name: "Testprojekt",
          auftragsnummer: "T-1",
          jahr: 2026,
          offerteSumme: { value: 1000, unit: "CHF" },
          wvSumme: null,
          projektStatus: { id: "1", name: "Offen" },
          projektleiter: { id: "5", username: "anna" },
          capabilities,
          projektKennzahlenList: { items: [] },
          kostenPositionenList: { items: [] },
          istWertList: { items: [] },
        },
      },
    },
  };
}

const kostenartMock = {
  request: { query: GET_KOSTENART_IDS },
  result: { data: { kostenartList: { items: [] } } },
};
const statusMock = {
  request: { query: GET_PROJEKT_STATUS_IDS },
  result: { data: { projektStatusList: { items: [{ id: "1", name: "Offen" }] } } },
};
const subscriptionMock = {
  request: { query: PROJEKT_DETAIL_SUBSCRIPTION, variables: { id: "1" } },
  result: { data: { onProjektChange: { action: "noop" } } },
  delay: 1000 * 60 * 60,
};
// Nötig, sobald canUpdate: true ist: die Komponente feuert dann die
// PROJEKTLEITER-Query (skip: !canEditData, siehe Step 4) — ohne passenden
// Mock schlägt MockedProvider mit "no mock found"/stderr-Rauschen fehl
// (reproduziert während der Implementierung).
const projektleiterMock = {
  request: { query: PROJEKTLEITER },
  result: { data: { benutzerList: { items: [{ id: "5", username: "anna" }] } } },
};

function renderPage(capabilities: { canUpdate: boolean; canDelete: boolean }) {
  return render(
    <MemoryRouter initialEntries={["/projekte/1"]}>
      <MockedProvider
        mocks={[
          projektMock(capabilities),
          kostenartMock,
          statusMock,
          subscriptionMock,
          projektleiterMock,
        ]}
      >
        <Routes>
          <Route path="/projekte/:id" element={<ProjektDetailPage />} />
        </Routes>
      </MockedProvider>
    </MemoryRouter>,
  );
}

describe("ProjektDetailPage – Bearbeiten-Button folgt projekt.capabilities.canUpdate", () => {
  it("zeigt den Bearbeiten-Button, wenn canUpdate true ist", async () => {
    renderPage({ canUpdate: true, canDelete: true });
    expect(await screen.findByText("Bearbeiten")).toBeInTheDocument();
  });

  it("versteckt den Bearbeiten-Button, wenn canUpdate false ist", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");
    expect(screen.queryByText("Bearbeiten")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProjektDetailPage`
Expected: FAIL — `capabilities` fehlt im lokalen `Projekt`-Typ/Query, Button folgt noch `canEdit(user)`.

- [ ] **Step 3: `GET_PROJEKT` in `queries.ts` anpassen**

```
      projektStatus {
        id
        name
      }
      projektleiter {
        id
        username
      }
      capabilities {
        canUpdate
        canDelete
      }
      projektKennzahlenList {
```

- [ ] **Step 4: `ProjektDetailPage.tsx` anpassen**

Imports:

```tsx
import { useMutation, useQuery, useSubscription } from "@apollo/client/react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Calculator, ChevronLeft, Database, Pencil } from "lucide-react";
import Layout from "../components/Layout";
import { GET_KOSTENART_IDS, GET_PROJEKT, GET_PROJEKT_STATUS_IDS, PROJEKTLEITER } from "../graphql/queries";
import {
  CREATE_KOSTEN_POSITION,
  DELETE_KOSTEN_POSITION,
  UPDATE_KOSTEN_POSITION,
  UPDATE_PROJEKT,
} from "../graphql/mutations";
import { PROJEKT_DETAIL_SUBSCRIPTION } from "../graphql/subscriptions";
import { chf, pct, signedPct, type GQLMeasurement } from "../utils/format";
import { getDeviation, DEV_STYLES, type DeviationLevel } from "../utils/deviation";
import { useAuth } from "../contexts/AuthContext";
```

(`useEffect` entfernt — der manuelle `fetch`-Effekt für `users` entfällt; Import von `canEdit, canViewFinancials` entfernt)

Typen:

```tsx
type Projekt = {
  id: string;
  name: string;
  auftragsnummer: string;
  jahr: number;
  offerteSumme: GQLMeasurement;
  wvSumme: GQLMeasurement | null;
  projektStatus: { id: string; name: string };
  projektleiter: { id: string; username: string } | null;
  capabilities: { canUpdate: boolean; canDelete: boolean };
  projektKennzahlenList: { items: ProjektKennzahlen[] };
  kostenPositionenList: { items: KostenPosition[] };
  istWertList: { items: IstwertItem[] };
};
```

```tsx
type UserOption = { id: string; username: string };
type ProjektleiterData = { benutzerList: { items: UserOption[] } };
```

Komponente:

```tsx
export default function ProjektDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const showFinancials = user?.capabilities.canViewFinanzen ?? false;

  const { data, loading, error, refetch } = useQuery<QueryData>(GET_PROJEKT, {
    variables: { id },
    skip: !id,
  });
  const canEditData = data?.projekt?.capabilities.canUpdate ?? false;

  const { data: kostenartData } = useQuery<KostenartIdsData>(GET_KOSTENART_IDS);
  const { data: projektStatusData } = useQuery<ProjektStatusIdsData>(GET_PROJEKT_STATUS_IDS);
  const { data: projektleiterData } = useQuery<ProjektleiterData>(PROJEKTLEITER, {
    skip: !canEditData,
  });
  const users = projektleiterData?.benutzerList.items ?? [];
  const artIdMap = new Map<string, string>(
    kostenartData?.kostenartList.items.map((a) => [a.schluessel, a.id]) ?? [],
  );

  useSubscription(PROJEKT_DETAIL_SUBSCRIPTION, {
    variables: { id },
    skip: !id,
    onData: () => { refetch(); },
  });

  const [editingHeader, setEditingHeader] = useState(false);
  const [headerForm, setHeaderForm] = useState<HeaderForm | null>(null);
  const [editingPos, setEditingPos] = useState<{
    id: string | null;
    artId: string;
    art: string;
    value: string;
  } | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const skipPosBlurRef = useRef(false);
```

(die `useState<UserOption[]>([])`-Zeile und der komplette `useEffect(() => { if (canEditData) { fetch("/api/users/") ... } }, [canEditData])`-Block entfallen ersatzlos)

`startEditHeader` vereinfacht sich, weil `p.projektleiter` jetzt direkt die ID trägt:

```tsx
  function startEditHeader() {
    if (!p) return;
    setHeaderForm({
      name: p.name,
      offerteSumme: String(p.offerteSumme.value),
      wvSumme: p.wvSumme ? String(p.wvSumme.value) : "",
      projektleiter: p.projektleiter?.id ?? "",
      projektStatus: p.projektStatus.id,
    });
    setEditingHeader(true);
    setMutationError(null);
  }
```

Anzeige außerhalb des Edit-Modus:

```tsx
                ) : (
                  <div className="mt-1 text-[15px] text-gray-900">{p.projektleiter?.username ?? "–"}</div>
                )}
```

Der "Bearbeiten"-Button-JSX (`{canEditData && !editingHeader && (...)}`) bleibt syntaktisch unverändert — `canEditData` ist jetzt aus `data?.projekt?.capabilities.canUpdate` abgeleitet statt aus `canEdit(user)`.

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- ProjektDetailPage`
Expected: PASS (beide Tests)

- [ ] **Step 6: Commit**

```bash
devcontainer exec --workspace-folder . git add frontend/src/graphql/queries.ts frontend/src/pages/ProjektDetailPage.tsx frontend/src/pages/ProjektDetailPage.test.tsx
devcontainer exec --workspace-folder . git commit -m "feat(frontend): ProjektDetailPage auf capabilities + Projektleiter-Objekt umgestellt"
```

---

## Task 10: Full-Gate-Verifikation

**Files:** keine (reine Verifikation)

**Interfaces:** keine

---

- [ ] **Step 1: Backend-Gate**

```bash
devcontainer exec --workspace-folder . uv run --group dev ruff check .
devcontainer exec --workspace-folder . uv run --group dev ruff format --check .
devcontainer exec --workspace-folder . uv run --group dev pytest
devcontainer exec --workspace-folder . uv run --group dev mypy src tests
```
Expected: alle vier grün (inkl. 100%-Coverage-Gate von `pytest`, falls konfiguriert)

- [ ] **Step 2: Frontend-Gate**

```bash
devcontainer exec --workspace-folder . npm --prefix frontend test
devcontainer exec --workspace-folder . npx --prefix frontend tsc --noEmit
```
Expected: beide grün. **Wichtig:** `npm run build` (= `vite build`, esbuild-basiert) prüft KEINE Typen und würde eine vergessene Anpassung (z. B. noch vorhandenes `allowedGroups` irgendwo, oder ein Import von `utils/permissions`) nicht zuverlässig aufdecken — verifiziert: `vite build` läuft auch mit einer nicht-existenten Prop klaglos durch, `tsc --noEmit` (nutzt das vorhandene `frontend/tsconfig.json`, `strict: true`, `noEmit: true` — offenbar für genau diesen Zweck vorgesehen, aber bisher in keinem npm-Script/Pre-commit-Hook verdrahtet) meldet es zuverlässig. `tsc --noEmit` ist daher hier der eigentliche Typ-Gate-Schritt, nicht `build`.

- [ ] **Step 3: Volles pre-commit-Gate**

```bash
devcontainer exec --workspace-folder . pre-commit run --all-files
```
Expected: `ruff (lint)`, `ruff (format check)`, `pytest (backend)`, `mypy (type check)`, `vitest (frontend)` — alle "Passed"

- [ ] **Step 4: Manuelle Stichprobe im Browser (optional, empfohlen)**

Kurzer manueller Smoke-Test über die `run`-Skill: Login als je ein User pro Rolle (Admin/Projektleiter/Betrachter/Monteur), prüfen:
- "Neues Projekt"-Button nur für Admin/Projektleiter sichtbar
- "Stundensätze"-Nav-Link nur für Admin/Projektleiter sichtbar
- Finanzspalten in Projektliste/-detail für Monteur ausgeblendet
- "Bearbeiten"-Button auf Projektdetailseite nur für Admin/Projektleiter sichtbar
- Projektleiter-Dropdown zeigt echte Namen, Speichern funktioniert
