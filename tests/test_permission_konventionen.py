"""Konventionstest: jeder GeneralManager deklariert seine Permissions selbst.

Hintergrund — warum dieser Test existiert:

`DEFAULT_PERMISSIONS` in `settings.py` ist als **Fehlernetz** gedacht, nicht als
Konfiguration. Ein Manager, der eine Regel nicht selbst hinschreibt, erbt sie
stillschweigend. Das ist zweimal teuer geworden:

1. `IstWert` und `ProjektKennzahlen` hatten kein eigenes `__read__` und waren
   dadurch über den damaligen Default `READ: ["public"]` für **jeden** lesbar,
   auch anonym.
2. `KostenPosition` verließ sich beim Schreiben auf `__based_on__ = "projekt"`.
   Das sieht aus wie Schutz, ist aber bei GraphQL-Mutationen wirkungslos: die
   Mutation-Schicht schreibt `projekt` vorher auf `projekt_id` um, die
   Delegation findet ihre Basis nicht mehr und fällt still auf den globalen
   Default zurück (Details in `reference.md` §5). Ein Monteur konnte so
   Kostenpositionen anlegen.

Beide Male war die Test-Suite grün. Dieser Test macht die Projektregel
„wir definieren immer explizit" überprüfbar: er schlägt fehl, sobald ein neuer
Manager eine Regel offenlässt — unabhängig davon, wie der Default gerade steht.
"""

from __future__ import annotations

from general_manager.interface import CalculationInterface
from general_manager.manager.meta import GeneralManagerMeta

# Regeln, die jeder Manager selbst deklarieren muss.
SCHREIB_REGELN = ("__create__", "__update__", "__delete__")


def _eigene_regeln(manager: type) -> set[str]:
    """Regeln, die die Permission-Klasse des Managers SELBST deklariert.

    Wichtig: `vars(Permission)` taugt dafür NICHT. GMs `__init_subclass__`
    schreibt nicht deklarierte Regeln als Default auf die Klasse
    (`cls.__read__ = list(default_read)`), sodass anschließend jede Regel im
    Klassen-Dict steht — ein Test darauf wäre immer grün. GM merkt sich die
    tatsächliche Deklaration vorher in `_explicit_permission_attrs`; das ist
    die einzige verlässliche Quelle.
    """
    permission = getattr(manager, "Permission", None)
    if permission is None:
        return set()
    explizit = getattr(permission, "_explicit_permission_attrs", None)
    assert explizit is not None, (
        f"{manager.__name__}.Permission hat kein _explicit_permission_attrs — "
        "GM hat dieses Attribut vermutlich umbenannt. Dieser Test prüft dann "
        "nichts mehr und muss an die neue API angepasst werden."
    )
    return set(explizit)


def _ist_nur_lesend(manager: type) -> bool:
    """CalculationInterface-Manager sind berechnet und erzeugen keine Mutations."""
    interface = getattr(manager, "Interface", None)
    return isinstance(interface, type) and issubclass(interface, CalculationInterface)


def _alle_manager() -> list[type]:
    manager = list(GeneralManagerMeta.all_classes)
    assert manager, "Manager-Registry ist leer — Test würde nichts prüfen"
    return manager


def test_jeder_manager_hat_eine_eigene_permission_klasse() -> None:
    ohne = [
        m.__name__ for m in _alle_manager() if getattr(m, "Permission", None) is None
    ]
    assert not ohne, f"Manager ohne Permission-Klasse: {sorted(ohne)}"


def test_jeder_manager_deklariert_read_selbst() -> None:
    fehlend = [
        m.__name__ for m in _alle_manager() if "__read__" not in _eigene_regeln(m)
    ]
    assert not fehlend, (
        "Diese Manager erben __read__ aus DEFAULT_PERMISSIONS statt es selbst zu "
        f"deklarieren: {sorted(fehlend)}. Der Default ist ein Fehlernetz, keine "
        "Konfiguration — die Regel gehört an den Manager."
    )


def test_schreibbare_manager_deklarieren_create_update_delete_selbst() -> None:
    fehlend: dict[str, list[str]] = {}
    for manager in _alle_manager():
        if _ist_nur_lesend(manager):
            continue
        eigene = _eigene_regeln(manager)
        offen = [regel for regel in SCHREIB_REGELN if regel not in eigene]
        if offen:
            fehlend[manager.__name__] = offen
    assert not fehlend, (
        "Diese Manager erben Schreibregeln aus DEFAULT_PERMISSIONS: "
        f"{fehlend}. __based_on__ ersetzt das NICHT — es ist bei "
        "GraphQL-Mutationen wirkungslos (reference.md §5)."
    )


def _nutzt_based_on(manager: type) -> bool:
    """Ob die Permission-Klasse `__based_on__` selbst setzt.

    Hier ist `vars()` richtig — anders als bei den vier Regeln materialisiert
    GMs `__init_subclass__` `__based_on__` nicht auf die Unterklasse, es steht
    also nur im Klassen-Dict, wenn es wirklich deklariert wurde.
    `_explicit_permission_attrs` führt `__based_on__` NICHT mit und taugt hier
    deshalb nicht.
    """
    permission = getattr(manager, "Permission", None)
    return permission is not None and "__based_on__" in vars(permission)


def test_based_on_manager_schreiben_ihre_schreibregeln_trotzdem_hin() -> None:
    """`__based_on__` darf nie der einzige Schreibschutz eines Managers sein.

    Greift auch dann, wenn ein Manager `__based_on__` erst später hinzubekommt —
    genau der Fall, in dem die trügerische Sicherheit entsteht.
    """
    fehlend: dict[str, list[str]] = {}
    for manager in _alle_manager():
        if not _nutzt_based_on(manager) or _ist_nur_lesend(manager):
            continue
        eigene = _eigene_regeln(manager)
        offen = [regel for regel in SCHREIB_REGELN if regel not in eigene]
        if offen:
            fehlend[manager.__name__] = offen
    assert not fehlend, (
        "Diese Manager nutzen __based_on__, deklarieren aber nicht alle "
        f"Schreibregeln selbst: {fehlend}. Die Delegation greift bei "
        "GraphQL-Create nicht (reference.md §5)."
    )
