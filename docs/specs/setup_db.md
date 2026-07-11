# Spec: DB-Reset & Dev-Daten-Bootstrap

## Ziel
Ein wiederverwendbares Skript, das die lokale Dev-Datenbank vollständig zurücksetzt
und mit reproduzierbaren Basisdaten füllt — damit Migrations-Resets schmerzfrei
sind und der Stand zwischen Entwicklern reproduzierbar bleibt.

## Artefakte
- `tools/setup_db.sh` — Orchestrierungs-Shell-Skript
- `src/apps/authentication/management/commands/setup_dev_data.py` — Django-Command für Daten-Bootstrap

## Verhalten von `tools/setup_db.sh`

Das Skript läuft Repo-Root-relativ und ist idempotent (mehrfaches Ausführen
liefert denselben Endzustand).

Reihenfolge:
1. `FORGE_ENV=dev` setzen (DB ist sonst Postgres laut `settings.py`).
2. `src/db.sqlite3` löschen, falls vorhanden.
3. In `src/apps/<app>/migrations/` alle `*.py` außer `__init__.py` entfernen,
   sowie das jeweilige `__pycache__/` säubern.
4. `python manage.py makemigrations` ausführen.
5. `python manage.py migrate` ausführen.
6. `python manage.py setup_dev_data` ausführen.

Fehler in Schritten 1–5 → Skript bricht ab (`set -euo pipefail`).
Fehler beim Bexio-Sync werden vom Command toleriert (siehe unten).

## Verhalten von `setup_dev_data`

Idempotent (`get_or_create` / `update_or_create`). Reihenfolge entscheidet
über die ID-Vergabe auf einer leeren DB.

### Gruppen (in dieser Reihenfolge anlegen)
| ID  | Name          |
| --- | ------------- |
| 1   | Admin         |
| 2   | Projektleiter |
| 3   | Betrachter    |
| 4   | Monteur       |

### Benutzer (in dieser Reihenfolge anlegen)
| ID  | Username | Passwort | is_superuser | is_staff | Gruppe        |
| --- | -------- | -------- | ------------ | -------- | ------------- |
| 1   | admin    | admin    | true         | true     | Admin         |
| 2   | simon    | simon    | false        | false    | Projektleiter |
| 3   | tina     | tina     | false        | false    | Betrachter    |

Passwörter werden via `set_password()` gesetzt (Hash). Bei bereits existenten
Usern werden Passwort und Gruppen-Zuweisung neu gesetzt, damit der Stand
reproduzierbar bleibt.

### Bexio-Sync
Nach dem User-Setup werden `sync_konten()` und anschließend
`sync_lieferantenrechnungen()` aufgerufen. Beide Aufrufe sind in `try/except`
gekapselt — Fehler werden geloggt (`logger.exception`) und an stdout gemeldet,
brechen den Befehl aber nicht ab. So bleibt der Auth-Bootstrap auch dann
brauchbar, wenn keine Bexio-Verbindung verfügbar ist.

Im Dev-Modus (`BEXIO_DEV_MODE=True`, kein Token) verwendet der `BexioClient`
ohnehin Fixture-Daten — Sync läuft also auch ohne Internet.

## Akzeptanzkriterien
- [ ] `bash tools/setup_db.sh` läuft auf einer frischen Repo-Kopie ohne Fehler durch.
- [ ] Nach dem Lauf existiert `src/db.sqlite3` neu.
- [ ] In jeder App liegt `0001_initial.py` (und ggf. weitere) neu erstellt vor.
- [ ] `auth_group` enthält genau die vier Gruppen mit IDs 1–4.
- [ ] `auth_user` enthält die drei User mit IDs 1–3, korrekten Passwörtern, korrekten Flags.
- [ ] `auth_user_groups` weist die User wie spezifiziert zu.
- [ ] Bexio-Tabellen sind im Dev-Mode mit Fixture-Daten gefüllt.
- [ ] Zweiter Lauf des Skripts produziert denselben Endzustand (idempotent).

## Out of Scope
- Postgres-Reset (Skript ist nur für SQLite-Dev-Modus).
- Produktions- oder Test-Container-Datenbank.
- Anlegen weiterer Domain-Daten (Projekte, KostenPositionen etc.).
