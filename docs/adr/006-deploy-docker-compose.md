# ADR 006 – Deployment als Single-Host Docker Compose nach dem Muster eines ähnlichen Projekts

**Datum:** 2026-09-13
**Status:** Akzeptiert

## Kontext

Forge soll beim Kunden (Handwerksbetrieb, ~10 Nutzer) auf einem einzelnen
Linux-Host laufen und von einer Person betrieben werden. In einem ähnlichen Projekt
existiert mit dessen `deploy/`-Ordner ein erprobtes Betriebskonzept für ein
GeneralManager-Backend derselben Toolchain (Django/Daphne, Celery, PostgreSQL,
Redis, Meilisearch): Compose mit Profilen, Datei-Secrets, nginx als einziger
Host-Port, Maintenance-Lease, Backup/Restore-Verification, Observability-Stack.

## Entscheidung

Forge übernimmt diesen Aufbau eins zu eins als `deploy/` (Ordnerstruktur,
Skripte, Profile, Alert-/Dashboard-Katalog, Runbook), mit zwei
`web`-Instanzen und ohne die referenzprojekt-spezifischen Integrationen
(Wiki.js, Legacy-Cache, PRO.FILE, MS-SSO, Netzlaufwerke, Sonder-Queues).
Das Backend liefert dafür Datei-Secrets (`NAME_FILE`), Health-Endpoints,
Prometheus-Metriken (django-prometheus, GM-GraphQL-Metriken, eigene API-/
Queue-Metriken), JSON-Logs und die WebSocket-Route für Subscriptions.

## Begründung

- Bekannter, dokumentierter Betriebspfad; Erfahrung aus dem Kundenbetrieb
  aus dem Referenzprojekt überträgt sich direkt.
- Ein Host, ein Compose-Projekt, ein Runbook: für einen einzelnen Betreiber
  überschaubar, Rollback über Git-Revision + verifiziertes Backup.
- Observability und Backup sind Teil des Basisaufbaus und nicht nachträglich
  angeflanscht; Alerts sind auf einen echten Metrikkatalog getestet.

## Konsequenzen

- Etwa 25 Container; Mindestausstattung 8 GB RAM, Testbetrieb auf einem
  Raspberry Pi 5 (arm64), alle Images sind multi-arch.
- Änderungen an der Topologie laufen über `deploy/compose.yml` plus die
  Contract-Tests unter `deploy/tests` und die Prometheus-Unit-Tests.
- Kein HSTS per Default, da Kunden-Zertifikate voraussichtlich selbstsigniert
  sind; mit CA-Zertifikat über `DJANGO_SECURE_HSTS_SECONDS` aktivierbar.

## Verworfene Alternativen

- **k3s/Kubernetes**: zu viel Betriebsaufwand für einen Host und einen Betreiber.
- **systemd-Units ohne Container**: verliert Isolation, Secrets-Handling und
  die erprobten Skripte.
- **Cloud-Hosting**: Kundendaten sollen im Intranet bleiben.
