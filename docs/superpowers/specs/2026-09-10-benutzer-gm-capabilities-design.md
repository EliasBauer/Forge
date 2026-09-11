# Benutzer als GM-Type + GraphQL-Capabilities (canX)

**Datum:** 2026-09-10
**Status:** Entwurf, genehmigt zur Umsetzung

## Kontext

Das Frontend prüft Berechtigungen aktuell rein über die Django-Gruppen des
eingeloggten Users (`AuthContext.user.groups`), abgefragt per REST-Endpoint
`GET /api/me/`. `frontend/src/utils/permissions.ts` dupliziert damit
Business-Regeln, die im Backend bereits als registrierte Permission-Strings
existieren (`isAdminGroup`, `isProjektleiter`, `isBetrachter`, `isMonteur` in
`apps/authentication/permission.py`, genutzt von `Projekt.Permission` u. a.).

Das führt zu zwei Problemen:

1. **Duplizierte Wahrheit:** ändert sich eine Regel im Backend (z. B. wer
   Projekte anlegen darf), muss `permissions.ts` synchron nachgezogen werden.
2. **Grobe Granularität:** das Frontend bekommt nur Rollen (`groups`), nicht
   die eigentliche Frage ("darf ich *dieses* Projekt bearbeiten?"). Komplexere
   Regeln (z. B. objektabhängig) lassen sich im FE gar nicht nachbilden, ohne
   Backend-Logik zu duplizieren.

GeneralManager bietet dafür zwei fertige, unabhängige Mechanismen:

- **Objekt-Capabilities** (`Permission.graphql_capabilities` +
  `permission_capability`/`object_capability`): hängen an einer konkreten
  Instanz, erzeugen ein `capabilities { ... }`-Feld auf dem jeweiligen
  GraphQL-Typ. Beispiel: "darf ich *dieses* Projekt bearbeiten?"
- **Globale Capabilities über `me`** (`GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER`):
  ein Provider liefert objektunabhängige Flags für den eingeloggten User,
  erzeugt automatisch ein `me { capabilities { ... } }`-Feld. Beispiel: "darf
  ich *überhaupt* neue Projekte anlegen?"

Beide setzen keinen GM-verwalteten User voraus. Zusätzlich soll aber
`django.contrib.auth.models.User` selbst zu einem vollwertigen GM-Manager
werden (`ExistingModelInterface`), damit `Projekt.projektleiter` als echtes
GraphQL-Objekt statt als roher String erscheint und künftige
Domain-Erweiterungen (weitere User-Relationen, Filter, Suche) denselben
GM-Layer nutzen wie jeder andere Manager.

## Ziel

- Neuer GM-Manager `Benutzer` (wrapt `auth.User`) und `Gruppe` (wrapt
  `auth.Group`) via `ExistingModelInterface`.
- `Projekt.projektleiter` wird von `User | None` auf `Benutzer | None`
  umgetypt — GraphQL liefert dafür ein Objekt (`{ id username }`) statt eines
  Strings.
- Objekt-Capability `Projekt.capabilities { canUpdate canDelete }` (Fall 1).
- Globale Capabilities über `me { username capabilities { canCreateProjekt
  canManageStundensaetze canViewFinanzen } }` (Fall 2), gespeist aus einem
  neuen Provider, der die bestehenden Gruppen-Prädikate wiederverwendet.
- Frontend liest Berechtigungen ausschließlich über diese beiden GraphQL-Wege;
  `utils/permissions.ts` und die REST-Endpunkte `/api/me/`, `/api/users/`
  entfallen.

## Nicht-Ziele

- Kein Custom-`AUTH_USER_MODEL`-Swap in Django. `auth.User` bleibt das
  Django-Model; `Benutzer` ist nur der GM-Wrapper darüber.
- Kein GraphQL-Create/Update/Delete für `Benutzer`/`Gruppe`. Nutzerverwaltung
  bleibt Django-Admin.
- `login_view`/`logout_view` (Session-Cookie-Handling) bleiben unverändert
  REST — nur "wer bin ich / was darf ich" wandert zu GraphQL.
- Keine Erweiterung der Capability-Liste über die hier genannten Flags
  hinaus (`canUpdate`, `canDelete` auf `Projekt`; `canCreateProjekt`,
  `canManageStundensaetze`, `canViewFinanzen` auf `me`). Weitere Manager
  (z. B. `Stundensatz`) folgen demselben Muster, sind aber nicht Teil dieser
  Spec.

## Design

### Backend

**Neue Datei `apps/authentication/models.py`** (die App hat aktuell keine):

```python
"""Beherbergt HistoricalUser, das simple_history dynamisch hier anhängt
(siehe managers.py). Keine eigenen Model-Definitionen."""
```

Notwendig, nicht nur Konvention: `simple_history.register(..., app="apps.authentication")`
importiert intern per `importlib.import_module("apps.authentication.models")`
und hängt die generierte `HistoricalUser`-Klasse per `setattr` dort an
(`simple_history/models.py::finalize()`). Ohne diese Datei schlägt die
Registrierung mit `ModuleNotFoundError` fehl — verifiziert per Probe gegen
den echten Ist-Zustand der App (kein `models.py` vorhanden). Passt auch zum
in der `general-manager`-Skill-Referenz dokumentierten Muster für
`ExistingModelInterface`: "Original in `models.py`, Wrapper in
`managers.py`".

**Neue Datei `apps/authentication/managers.py`:**

```python
from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.models import Group, User
from general_manager import (
    AdditiveManagerPermission,
    ExistingModelInterface,
    GeneralManager,
)
from simple_history import register

from general_manager.interface.utils.history import DatabaseAwareHistoricalRecords

# Muss vor den Manager-Klassendefinitionen laufen: registriert die History
# BEIDER Django-Modelle unter dem "apps.authentication"-App-Label — nicht nur
# User. Grund: GMs ensure_history() läuft für JEDEN ExistingModelInterface-
# Manager automatisch, also auch für Gruppe. Wird nur User hier
# vorregistriert, versucht makemigrations für Group trotzdem eine Migration
# nach .venv/.../django/contrib/auth/migrations/ zu schreiben (reproduziert
# gegen general_manager 0.79.3 während der Implementierung — siehe Plan,
# Korrektur 2). Mit beiden Modellen vorregistriert ist
# ExistingModelResolutionCapability.ensure_history() für beide ein No-op.
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

    Nötig, damit Benutzer.groups_list als echte, filterbare Relation
    (nicht als String-Skalar) im GraphQL-Schema erscheint — verifiziert:
    GM löst Relationsfelder nur zu einem Objekttyp auf, wenn das
    Zielmodell selbst ein registrierter GM-Manager ist.
    """

    id: int
    name: str

    class Interface(ExistingModelInterface):
        model = Group

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["never"]
        __update__ = ["never"]
        __delete__ = ["never"]


class Benutzer(GeneralManager):
    """GM-Wrapper um django.contrib.auth.models.User."""

    id: int
    username: str
    is_active: bool

    class Interface(ExistingModelInterface):
        # Direkter User-Klassenimport, NICHT settings.AUTH_USER_MODEL
        # (String): Letzteres löst apps.get_model() zur Klassendefinitions-
        # zeit aus, was mypys django-stubs-Plugin mit einem INTERNAL ERROR
        # (AppRegistryNotReady) crasht — reproduziert während der
        # Implementierung (siehe Plan, Korrektur 1). Mit der direkten Klasse
        # entfällt der apps.get_model()-Aufruf komplett.
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

GM baut für jeden `ExistingModelInterface`-Manager automatisch eine
`Factory`-Klasse, auch ohne eigene Deklaration (verifiziert:
`hasattr(Benutzer, "Factory")` → `True`). Wir deklarieren bewusst keine
eigene `Benutzer.Factory` — Create/Update sind ohnehin auf `["never"]`
gesperrt, und bestehende Backend-Tests legen User bereits direkt über
Django-ORM an (`User.objects.create_user(...)`, siehe
`test_authentication.py`). Sollte künftig `seed_manager_landscape` (§7 der
GM-Referenz) für `Benutzer` genutzt werden, sind die Auto-Factory-Defaults
(insbesondere `password`) vor dem Einsatz zu prüfen.

Da `User` ein `is_active`-Feld hat, aktiviert GM für `Benutzer` automatisch
Soft-Delete (verifiziert: `is_soft_delete_enabled(Benutzer.Interface)` →
`True`, ohne dass wir das explizit konfigurieren). `benutzerList`/`.filter()`
liefern damit standardmäßig nur `is_active=True`-User — deaktivierte
Django-User erscheinen nicht im `PROJEKTLEITER`-Dropdown, außer per
`includeInactive: true` explizit angefordert. Das ist das gewünschte
Verhalten, sollte aber im Implementierungsschritt nicht überraschen.

**Neues Permission-Prädikat** in `apps/authentication/permission.py`:

```python
@register_permission("never")
def _permission_never(_instance, _user, _config) -> bool:
    return False
```

(`{"read": []}` bedeutet bei GM "erlaubt", nicht "verboten" — eine leere
Regelliste wird als `True` gewertet, verifiziert gegen
`ManagerBasedPermission.__check_specific_permission`. Für "nie lesbar"
braucht es ein Prädikat, das immer `False` liefert.)

**Neuer Capabilities-Provider** `apps/authentication/graphql_capabilities.py`:

```python
from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from general_manager.permission import object_capability

from apps.authentication.permission import _is_in_group


def _user_or_none(user: object) -> AbstractBaseUser | None:
    """Nur eingeloggte User weiterreichen — AnonymousUser zählt als "kein
    User", geprüft BEVOR irgendeine Gruppen-Regel läuft.

    Ohne diese Schranke wäre canViewFinanzen für nicht eingeloggte Requests
    fälschlich True: `not _is_in_group(AnonymousUser, "Monteur")` ist True,
    weil AnonymousUser in keiner Gruppe steckt — die "not Monteur"-Regel
    greift dann versehentlich positiv (reproduziert während der
    Implementierung). Das Frontend prüfte das bisher explizit über
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

Benannte `def`-Funktionen statt Lambdas: mit Lambdas crasht mypy strict mit
`Argument 1 to "_is_in_group" has incompatible type "object"; expected
"AbstractBaseUser | AnonymousUser"` (reproduziert), weil der von GM erwartete
Evaluator-Typ `Callable[[object, object], bool]` ist — die `isinstance`-
Schranke in `_user_or_none` engt `object` mypy-sauber ein.

Kein `resolve_username` nötig — verifiziert per Probe gegen den generierten
`Me`-Typ: fehlt ein `resolve_<feld>`, fällt GM auf `getattr(user, feldname)`
zurück, was für `username` direkt funktioniert.

**Settings** (`forge/settings.py`, Ergänzung im bestehenden `GENERAL_MANAGER`-Dict):

```python
GENERAL_MANAGER = {
    ...,
    "GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER": (
        "apps.authentication.graphql_capabilities.CurrentUserCapabilities"
    ),
}
```

(`get_setting()` sucht zuerst in diesem Dict — verifiziert gegen
`general_manager/conf.py`. Ein Top-Level-Setting würde zwar auch
funktionieren, aber Forge hat bereits das `GENERAL_MANAGER`-Dict als
zentrale Stelle für alle GM-Settings.)

**`apps/authentication/apps.py`:** `ready()` importiert zusätzlich
`apps.authentication.managers` (analog zum bestehenden Muster in
`apps/projekt/apps.py`, das `apps.projekt.models` importiert):

```python
def ready(self) -> None:
    importlib.import_module("apps.authentication.permission")
    importlib.import_module("apps.authentication.managers")
```

**`apps/projekt/models/projekt.py`:**

- Import `from django.contrib.auth.models import User` entfällt.
- Annotation `projektleiter: User | None` → `projektleiter: Benutzer | None`
  (Import aus `apps.authentication.managers`).
- Das Django-FK-Feld selbst (`models.ForeignKey("auth.User", ...)`) bleibt
  unverändert — nur die Manager-Typannotation für die GraphQL-Auflösung
  ändert sich.
- `create()`/`update()`: die bestehende `projektleiter` → `projektleiter_id`
  Remapping-Logik bleibt unverändert (Mutation-Input nimmt weiterhin eine
  rohe ID als String entgegen, das war schon vor dieser Änderung so gelöst).
- `Permission.graphql_capabilities` als leeres `ClassVar` deklarieren; die
  eigentliche Zuweisung passiert NICHT auf Modulebene, sondern in einer
  Funktion, aufgerufen aus `ProjektConfig.ready()`:

```python
class Permission(AdditiveManagerPermission):
    __read__ = ["isAdminGroup", "isProjektleiter", "isBetrachter"]
    __create__ = ["isAdminGroup", "isProjektleiter"]
    __update__ = ["isAdminGroup", "isProjektleiter"]
    __delete__ = ["isAdminGroup", "isProjektleiter"]
    graphql_capabilities: ClassVar[tuple[GraphQLPermissionCapability, ...]] = ()


def _register_graphql_capabilities() -> None:
    """Von ProjektConfig.ready() aufgerufen, NICHT auf Modulebene.

    Projekt.Permission.graphql_capabilities = (...) auf Modulebene würde beim
    Import von projekt.py über Projekt.Permission (Metaclass-Zugriff) GMs
    Lazy-Attribute-Initialisierung auslösen, die den vollen App-Registry
    braucht (apps.get_models()). Zur normalen Django-Laufzeit ist das kein
    Problem (Modelle sind beim Import längst geladen) — mypys
    django-stubs-Plugin importiert Model-Module aber in einer Reihenfolge,
    in der die Registry noch nicht vollständig ist, und crasht dabei mit
    einem INTERNAL ERROR (reproduziert während der Implementierung, siehe
    Plan, Korrektur 3). ready() läuft garantiert erst NACH dem Laden aller
    Apps und wird von django-stubs nicht mit-ausgeführt.
    """
    Projekt.Permission.graphql_capabilities = (
        permission_capability(Projekt, "update", name="canUpdate"),
        permission_capability(Projekt, "delete", name="canDelete"),
    )
```

`apps/projekt/apps.py`s `ready()` importiert zusätzlich diese Funktion und
ruft sie auf (analog zum `authentication`-App-Muster oben).

**Entfernt:**

- `apps/authentication/views.py`: `users_view`, `current_user_view`.
- `apps/authentication/urls.py`: die zugehörigen `path()`-Einträge
  (`"me/"`, `"users/"`). `login_view`/`logout_view` bleiben.

### Migrationen

- Neue `apps/authentication/migrations/` (App hat aktuell keine) mit
  `0001_initial.py` für `HistoricalUser` unter dem `apps.authentication`-Label.
- Keine Migration für `apps/projekt` — `projektleiter` bleibt derselbe FK,
  nur der Python-Typ auf der Manager-Klasse ändert sich.
- Keine Migration für `User`/`Group`/`Permission` selbst — `ExistingModelInterface`
  legt keine neue Tabelle an.

### GraphQL — resultierende Queries

```graphql
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

query Projektleiter {
  benutzerList(filter: { groupsList: { any: { name: "Projektleiter" } } }) {
    items { id username }
  }
}

query ProjektDetail($id: ID!) {
  projekt(id: $id) {
    id
    projektleiter { id username }
    capabilities { canUpdate canDelete }
    ...
  }
}
```

Der `groupsList`-Filterpfad ist gegen den generierten Filtertyp verifiziert:
`Benutzer`-Filter hat `groupsList: { any/none: GruppeFilter }`, `GruppeFilter`
hat `name` (+ `name__icontains` etc.) — nur möglich, weil `Gruppe` selbst ein
GM-Manager ist.

### Fehlerbehandlung

- Ein werfender Capability-Evaluator wird von GM abgefangen, geloggt und als
  `False` gewertet (`CapabilityEvaluationContext.evaluate`) — nie ein
  GraphQL-Fehler an den Client.
- Gesperrte Felder (`password`, `is_superuser` für Nicht-Admins) liefern
  `null`, keinen Error.
- `me` für einen nicht eingeloggten Request: `info.context.user` ist
  `AnonymousUser`, nie `None` — `me` selbst ist also nie `null`.
  `AnonymousUser.username` ist `""`. Alle Gruppen-Capability-Checks liefern
  `False` (kein Crash, `AnonymousUser.groups` existiert als leeres
  Queryset). Das Frontend muss daher "nicht eingeloggt" an `username === ""`
  festmachen, nicht an `me === null`.

### Frontend

**`frontend/src/graphql/queries.ts`:**

- Neue Query `ME` (siehe oben).
- Neue Query `PROJEKTLEITER` (ersetzt `/api/users/`, siehe oben).
- `GET_PROJEKTE`, `SEARCH_PROJEKTE`, `GET_PROJEKT`: `projektleiter` →
  `projektleiter { id username }`.
- `GET_PROJEKT`: zusätzlich `capabilities { canUpdate canDelete }`.

**`frontend/src/contexts/AuthContext.tsx`:**

- `AuthUser` verliert `groups: UserGroup[]`, `isStaff: boolean`; bekommt
  `capabilities: { canCreateProjekt: boolean; canManageStundensaetze: boolean;
  canViewFinanzen: boolean }`.
- `useEffect`-Ladepfad: `fetch("/api/me/")` → `apolloClient.query({ query: ME })`.
  "Nicht eingeloggt" = `data.me.username === ""` → `user` bleibt `null`.
- `login()`: REST-Call bleibt (Session-Cookie), aber nach Erfolg wird die
  `ME`-Query erneut abgefragt statt die REST-Response direkt als `AuthUser`
  zu übernehmen (Cookie muss zuerst gesetzt sein).
- `UserGroup`-Type entfällt.

**`frontend/src/utils/permissions.ts`:** Datei entfällt komplett. Aufrufer
lesen die Capability direkt:

| Bisher | Neu |
|---|---|
| `canCreateProject(user)` | `user.capabilities.canCreateProjekt` |
| `canManageStundensaetze(user)` | `user.capabilities.canManageStundensaetze` |
| `canViewFinancials(user)` | `user.capabilities.canViewFinanzen` |
| `canEdit(user)` (in `ProjektDetailPage`) | `projekt.capabilities.canUpdate` (aus der `GET_PROJEKT`-Antwort, nicht mehr aus `user`) |

**`frontend/src/components/ProtectedRoute.tsx`:** Prop `allowedGroups?:
UserGroup[]` → `requiredCapability?: keyof AuthUser["capabilities"]`; die
Prüfung wird `!user.capabilities[requiredCapability]`.

**`frontend/src/App.tsx`:** `allowedGroups={["Admin", "Projektleiter"]}` bei
`/projekte/neu` → `requiredCapability="canCreateProjekt"`; bei
`/stundensaetze` → `requiredCapability="canManageStundensaetze"`.

**`frontend/src/pages/ProjektNeuPage.tsx`, `ProjektDetailPage.tsx`:**
`fetch("/api/users/")` → Apollo-Query `PROJEKTLEITER`. Das bisherige
Username-Matching (`users.find(u => u.username === p.projektleiter)`)
entfällt, da `p.projektleiter` jetzt direkt `{ id, username }` liefert.

**`frontend/src/pages/ProjektListePage.tsx`:** `<Avatar name={p.projektleiter}
/>` → `<Avatar name={p.projektleiter?.username ?? "—"} />`.

### Tests

**Backend:**

- `apps/authentication/tests/test_benutzer.py` (neu): `password` liefert
  für jede Rolle `null`; `is_superuser`/`user_permissions_list`/
  `log_entry_list` nur für Admin sichtbar, sonst `null`; Create/Update/Delete
  via GM werfen `PermissionError` für jede Rolle.
- `apps/authentication/tests/test_gruppe.py` (neu): Lesen erlaubt,
  Create/Update/Delete verboten.
- `apps/projekt/tests/test_projekt.py`: `capabilities.canUpdate`/`canDelete`
  je Rolle (Admin/Projektleiter/Betrachter/Monteur).
- `apps/authentication/tests/test_authentication.py`: neue Tests für
  `CurrentUserCapabilities` (alle drei Flags je Rolle + anonym), analog zu
  den bestehenden `PermissionIsAdminTest`/`PermissionIsProjektleiterTest`.
- `tests/test_graphql_queries.py`: `projektleiter` als Objekt statt String
  in bestehenden Query-Strings.

**Frontend:**

- `AuthContext`- und `ProtectedRoute`-Tests auf `capabilities` statt
  `groups` umstellen.
- `ProjektListePage.test.tsx`: Mock-User (`groups: ["Admin"]`) → Mock-User
  mit `capabilities`-Objekt; `projektleiter`-Mock-Daten von String auf
  `{ id, username }` umstellen.

## Offene Risiken

- `groupsList`-Filter-Syntax (`{ any: { name: "Projektleiter" } }`) ist gegen
  eine minimale Probe-Registrierung von `Benutzer`/`Gruppe` verifiziert, aber
  noch nicht im vollen Forge-Schema (mit allen bestehenden Managern) getestet
  — mögliche Namenskollisionen mit anderen `Gruppe`-artigen Typen sind vor der
  Umsetzung zu prüfen.
- `HistoricalUser`-Migration unter `apps.authentication`: die
  `simple_history.register(...)`-Reihenfolge (vor der `Benutzer`-Klasse) ist
  zeitkritisch — ein versehentlicher Reimport-/Reload-Pfad (z. B. Django Dev
  Autoreload) könnte doppelte Registrierung auslösen. Der
  `if not hasattr(...)`-Guard in `managers.py` deckt das ab, sollte aber im
  Implementierungsschritt gezielt unter Autoreload getestet werden.
