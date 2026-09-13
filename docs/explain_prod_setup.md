# Das Produktions-Setup erklärt

Dieses Dokument erklärt, *was* in `deploy/` steht, *warum* es so gebaut ist
und *wie du damit umgehst*, wenn etwas nicht läuft. Es setzt keine
DevOps-Erfahrung voraus. Die Kurzanleitung zum Starten ist
[`start_prod.md`](start_prod.md), das Betriebshandbuch mit allen Befehlen ist
[`deploy/README.md`](../deploy/README.md), die Entscheidung dahinter
[ADR 006](adr/006-deploy-docker-compose.md).

---

## 1. Das große Bild

```
                         Browser / Client
                               │  https (443)  – einziger offener Port
                               ▼
                        ┌──────────────┐
                        │    nginx     │  TLS, Frontend-Dateien, Reverse Proxy,
                        │  (Container) │  drei Hostnamen: App / Monitoring / Admin
                        └──┬───────┬───┘
      /graphql /api /admin │       │ monitoring.… → Grafana,  db.… → pgAdmin
                           ▼       ▼
                 ┌──────────────┐
                 │ web ×2       │  Django + GeneralManager, Daphne (ASGI:
                 │ (daphne)     │  HTTP und WebSocket in einem Prozess)
                 └──┬───────────┘
          SQL       │  Cache, Channel-Layer, Task-Queue
     ┌──────────────┼────────────────┐
     ▼              ▼                ▼
┌──────────┐   ┌─────────┐   ┌──────────────┐
│ pgbouncer│   │  redis  │   │ meilisearch  │
│ (Pool)   │   │         │   │ (Volltext)   │
└────┬─────┘   └────┬────┘   └──────────────┘
     ▼              │
┌──────────┐        │   ┌──────────────┐  ┌──────────────┐
│ postgres │        └──▶│ celery-worker│  │ celery-beat  │  Hintergrund-Jobs
│  (Daten) │            │ (arbeitet)   │  │ (Zeitplan)   │  (Bexio-Sync, Suchindex)
└──────────┘            └──────────────┘  └──────────────┘

Daneben, optional per Profil:
  observability: prometheus, alertmanager, grafana, loki, alloy, blackbox,
                 node/postgres/pgbouncer/redis/celery/nginx-exporter, pushgateway
  administration: pgadmin
  backup / restore-verification: einmalige Jobs
```

Ein einzelner Linux-Host, ein Docker-Compose-Projekt namens `forge`, rund
25 Container. Von außen erreichbar ist **nur nginx** (Port 80 leitet auf 443
um). Alles andere redet über interne Docker-Netze miteinander.

---

## 2. Die wichtigsten Begriffe

| Begriff | Bedeutung für Forge |
| --- | --- |
| **Image** | Eine fertig gebaute, unveränderliche Vorlage (z. B. `forge-backend`, `postgres:17-alpine`). Wird aus einem `Dockerfile` gebaut oder von Docker Hub geladen. |
| **Container** | Ein laufender Prozess aus einem Image, mit eigenem Dateisystem und Netzwerk. Stirbt der Prozess, ist der Container weg; Daten überleben nur in Volumes. |
| **Compose** | `docker compose` liest `compose.yml` und startet alle Container als eine Einheit („Projekt"). Wir rufen es nie direkt auf, sondern über `scripts/compose.sh` (lädt `.env`, löst die Deploy-Gruppe auf). |
| **Profil** | Eine Gruppe optionaler Dienste in `compose.yml`. Ohne Profil laufen nur die Kern-Dienste. `--profile observability` schaltet das Monitoring dazu, `administration` pgAdmin, `backup` und `restore-verification` die Einmal-Jobs. |
| **Bind-Mount** | Ein Host-Verzeichnis, das in einen Container eingehängt wird. Alle persistenten Daten liegen so unter `/srv/forge/data/…` und überleben Container-Neustarts, Updates und `rm`. |
| **Netzwerk** | Docker-interne Netze (`ingress`, `application`, `data`, `observability`, …). Ein Container erreicht nur, was im selben Netz ist. Postgres hängt nur im Netz `data`; von außen kommt niemand dran. |
| **Secret** | Eine Datei in `deploy/secrets/`, die Compose als `/run/secrets/<name>` in den Container legt. Passwörter stehen nie in `.env` oder in Umgebungsvariablen, die man mit `docker inspect` lesen könnte. |
| **Healthcheck** | Ein Befehl, den Docker regelmäßig im Container ausführt. `healthy` bedeutet z. B. bei `web`: `GET /health/live/` antwortet 200. Abhängige Dienste starten erst, wenn ihre Vorgänger `healthy` sind. |
| **Replikat** | Mehrere gleichartige Container eines Dienstes. `web` läuft zweimal (`WEB_REPLICAS=2`); nginx verteilt die Anfragen. |
| **Reverse Proxy** | nginx nimmt alle Anfragen entgegen und reicht sie an den passenden Dienst weiter. Der Browser sieht nie `web:8000` oder `grafana:3000`. |
| **TLS** | Verschlüsselung (https). nginx hält Zertifikat und Schlüssel; die Container dahinter sprechen unverschlüsselt im internen Netz. |

---

## 3. Die Dienste im Einzelnen

### Kern (läuft immer)

**nginx** (`deploy/nginx/`). Baut beim Image-Build das React-Frontend (`npm ci`,
`vite build`) und liefert es als statische Dateien aus. Leitet `/graphql`,
`/api`, `/admin`, `/health` an `web` weiter, inklusive WebSocket-Upgrade für
GraphQL-Subscriptions (Live-Updates). `/static/` (Django-Admin-CSS) kommt aus
dem Bind-Mount `static`. Zwei weitere Hostnamen: `MONITORING_DOMAIN` → Grafana,
`ADMIN_DOMAIN` → pgAdmin, letzterer zusätzlich hinter HTTP-Basic-Auth
(`admin_htpasswd.txt`). Liegt die Datei `/run/forge/maintenance` (auf dem
Host: `/srv/forge/data/runtime/maintenance`), antwortet nginx auf alles mit
einer Wartungsseite (503). `/metrics` wird bewusst *nicht* nach außen geleitet.

**web** (`deploy/backend/Dockerfile`). Django mit GeneralManager, gestartet
über Daphne, einen ASGI-Server, der HTTP und WebSockets in einem Prozess
bedient. Zwei Replikate, damit ein hängender Prozess die App nicht lahmlegt
und Updates unterbrechungsarm sind. Das Container-Dateisystem ist
schreibgeschützt (`read_only`), nur `/tmp` ist beschreibbar. Liest alle
Secrets über `*_FILE`-Variablen (`forge/env.py`). Bietet `/health/live/`
(Prozess lebt), `/health/ready/` (Datenbank und Cache erreichbar),
`/health/maintenance/` und `/metrics` (Prometheus).

**celery-worker** und **celery-beat**. Celery ist das Hintergrund-Job-System:
Beat ist der Zeitplan (z. B. der Bexio-Sync mittwochs 02:00 und die
Suchindex-Reconciliation alle 30 s), der Worker führt die Jobs aus. Beide
nutzen Redis als Nachrichtenkanal. Beat läuft genau einmal (sonst würden Jobs
doppelt geplant), der Worker kann skaliert werden.

**postgres**. Die Datenbank, PostgreSQL 17. Daten liegen in
`/srv/forge/data/postgres`. Nur im Netz `data`, kein Host-Port. Das Passwort
kommt aus `postgres_password.txt`; beim allerersten Start initialisiert das
Image damit die Datenbank. Später das Passwort zu ändern erfordert ein
`ALTER USER` in der laufenden Datenbank (siehe README „PostgreSQL-Passwort
stimmt nicht").

**pgbouncer**. Ein Verbindungs-Pool vor Postgres. Jede Django-Anfrage öffnet
sonst eine eigene Datenbankverbindung; PostgreSQL verträgt davon nur wenige
hundert. pgBouncer hält einen kleinen Pool offen und verteilt ihn. Deshalb
läuft Django mit `CONN_MAX_AGE=0` und ohne Server-Side-Cursors.
`django-migrate` und `search-index` umgehen den Pool und gehen direkt zu
Postgres, weil Migrationen längere Transaktionen brauchen.

**redis**. In-Memory-Speicher mit drei Rollen: Django-Cache, Channel-Layer
(verteilt WebSocket-Ereignisse zwischen den beiden `web`-Replikaten) und
Celery-Broker. Persistiert per Append-Only-File nach `/srv/forge/data/redis`;
ein Verlust wäre verschmerzbar (Cache und Queue bauen sich neu auf).

**meilisearch**. Volltext-Suchmaschine für die Projektsuche. Der Master-Key
ist ein Secret. Der Index ist ableitbar: `search-index --reindex` baut ihn
jederzeit aus der Datenbank neu auf; deshalb wird er nicht gesichert.

**django-migrate** (einmalig bei jedem Deploy). Führt `check --deploy`
(Django-Sicherheitsprüfung), `migrate` (Datenbankschema), `collectstatic`
(Admin-Dateien nach `/static`) und `create_groups` (die vier Benutzergruppen)
aus. Erst wenn dieser Container mit Exit 0 fertig ist, starten `web` und
Celery.

**search-index** (Profil `deployment`, einmalig). Baut alle Suchindizes neu
auf. Schlägt das fehl, bricht das Deployment ab.

### Observability (Profil `observability`)

Der Grundgedanke: **Metriken** (Zahlen über Zeit), **Logs** (Textzeilen) und
**Alerts** (Regeln auf Metriken) in drei Systemen, zusammengeführt in Grafana.

- **prometheus** sammelt alle 15 s Metriken, indem es die Dienste abfragt
  („scrapen"): `web` (Django- und GraphQL-Metriken), die Exporter, sich selbst.
  Es wertet auch die Alert-Regeln aus. Speichert 45 Tage oder 10 GB.
- **Exporter** übersetzen Dienste ohne eigene Prometheus-Schnittstelle:
  `node-exporter` (CPU, RAM, Platte des Hosts), `postgres-exporter`,
  `pgbouncer-exporter`, `redis-exporter`, `celery-exporter` (Tasks, Worker),
  `nginx-exporter` (Verbindungen, Requests).
- **blackbox-exporter** prüft von außen: ruft `https://<APP_DOMAIN>/health/live/`
  und die GraphQL-Probe auf wie ein Benutzer und misst Erfolg, Dauer und
  Zertifikatsablauf. Damit merkt man auch Fehler in nginx oder TLS, die
  interne Metriken nicht zeigen.
- **pushgateway** nimmt Metriken von Einmal-Jobs entgegen (Backup, Restore-
  Verification, Celery-Queue-Tiefe), die Prometheus sonst nie „sehen" würde,
  weil sie nur Sekunden laufen.
- **alertmanager** bekommt feuernde Alerts von Prometheus, gruppiert sie,
  unterdrückt Folgefehler (Inhibition) und verschickt E-Mail (SMTP) und
  optional Microsoft-Teams-Nachrichten. Alerts mit `notification_scope:
  business_hours` werden nur Mo–Fr 07–18 Uhr (Europe/Zurich) zugestellt,
  `always` immer, `none` nie (nur im Dashboard sichtbar).
- **alloy** liest die Log-Ausgabe aller Container über den Docker-Socket,
  extrahiert das Log-Level (Django schreibt JSON, Celery Klartext) und
  schickt alles an **loki**, die Log-Datenbank (7 Tage). Alloy liefert
  zusätzlich Container-Metriken (CPU/RAM je Container, cAdvisor).
- **grafana** ist die Oberfläche. Datasources (Prometheus, Loki) und 20
  Dashboards werden beim Start aus `deploy/grafana/` provisioniert; in
  Grafana selbst ist nichts editierbar (`editable: false`), damit der Stand
  im Repo die Wahrheit bleibt. Die Dashboards sind aus
  `grafana/scripts/dashboard_specs.py` generiert.

Wo anfangen: Grafana → Ordner **Operations** → **Forge Overview**. Von dort
verlinken die Panels in die thematischen Dashboards (API, Async & Redis,
Postgres & PgBouncer, Search, Host & Containers, Continuity, Logs).

### Administration (Profil `administration`)

**pgadmin** ist eine Web-Oberfläche für PostgreSQL. Sie ist zweifach
geschützt (nginx-Basic-Auth, dann pgAdmin-Login) und kennt den Server
`postgres` bereits (`pgadmin/servers.json`); das Datenbank-Passwort fragt
pgAdmin beim Verbinden ab. Für den Normalbetrieb nicht nötig, aber
praktisch für Datenkorrekturen.

### Backup und Restore (Profile `backup`, `restore-verification`)

**backup** (Einmal-Job): `pg_dump` der Datenbank, Prüfung mit
`pg_restore --list`, Manifest mit Git-Revision, SHA-256-Summen, dann
atomares Umbenennen nach `/srv/forge/data/backups/<Zeitstempel>/` und
Kopie (`rsync`) nach `BACKUP_SHARE`. Retention: 30 tägliche, 12 monatliche.
Metriken gehen an den Pushgateway; Alerts schlagen an, wenn das letzte
erfolgreiche Backup älter als 26 h (Warnung) bzw. 50 h (kritisch) ist.

**restore-verification**: startet ein *separates, leeres* PostgreSQL in einem
isolierten Netz, spielt ein Backup ein und lässt Django-Checks laufen.
Beweist, dass das Backup wirklich wiederherstellbar ist, ohne die
Produktionsdatenbank zu berühren. Alert, wenn das länger als 8 bzw. 15 Tage
her ist.

**restore-postgres.sh**: der echte Notfall-Restore in die Produktionsdatenbank.

---

## 4. Netzwerke und Ports

| Netz | Wer | Zweck |
| --- | --- | --- |
| `ingress` | nginx, grafana, pgadmin, blackbox | Was nginx nach außen vermittelt |
| `application` | web, celery, pgbouncer, redis, meilisearch, exporter | Laufzeit der App |
| `data` | postgres, pgbouncer, django-migrate, backup, postgres-exporter | Datenbank-Seite |
| `observability` | Prometheus, Loki, Alloy, Alertmanager, Exporter, Pushgateway | Monitoring |
| `alerting-egress` | alertmanager | Ausgehende Benachrichtigungen |
| `restore-verification` | restore-postgres, restore-verify (internal) | Isolierte Restore-Probe |

Host-Ports: nur `HTTP_PORT` (80) und `HTTPS_PORT` (443) auf nginx. Der
Preflight bricht ab, wenn ein Stateful-Dienst versehentlich einen Port
veröffentlicht.

---

## 5. Sicherheitskonzept

- **Secrets als Dateien** in `deploy/secrets/` (gitignored), Modus `0640`,
  Gruppe `forge-deploy`. Compose reicht sie als `/run/secrets/*` in genau die
  Container, die sie brauchen. Der Preflight lehnt Platzhalter (`CHANGE_ME`)
  und weltlesbare Dateien ab.
- **Deploy-Gruppe** `forge-deploy`: Operatoren sind Mitglied, die numerische
  GID wird beim Start ermittelt und als Zusatzgruppe in die
  Secret-Konsumenten gereicht. So können Container mit anderer UID die
  gruppenprivaten Dateien lesen, ohne dass sie weltlesbar wären.
- **Feste UIDs**: Backend läuft als `appuser` (1000), Prometheus/Alertmanager/
  Pushgateway als 65534, Grafana 472, Loki 10001, pgAdmin 5050. Jeder
  Bind-Mount gehört genau seinem Dienst; der Preflight prüft das.
- **Härtung**: `no-new-privileges`, `cap_drop: ALL` (keine Root-Fähigkeiten),
  `read_only` Root-Dateisystem für `web` und Celery, keine Host-Ports außer
  nginx. Alloy braucht als Einziger privilegierten Host-Zugriff (Docker-Socket,
  `/proc`, `/sys`) – das ist gleichbedeutend mit Host-Vertrauen und in
  `compose.yml` als solches kommentiert.
- **Django hinter nginx**: `SECURE_PROXY_SSL_HEADER` (Django vertraut dem
  `X-Forwarded-Proto` von nginx), Secure-Cookies, `ALLOWED_HOSTS` und
  `CSRF_TRUSTED_ORIGINS` aus `.env`. Der Secret-Key ist in Produktion
  Pflicht; ohne ihn startet die App nicht.
- **HSTS** ist absichtlich aus: mit selbstsignierten Zertifikaten würde es
  Browser dauerhaft aussperren. Mit einem Zertifikat der Firmen-CA
  `DJANGO_SECURE_HSTS_SECONDS=31536000` setzen.
- **Nicht abgedeckt**: Host-Firewall, Betriebssystem-Updates, physischer
  Zugriff, externes Monitoring des Hosts selbst (fällt der Host aus, fällt
  auch das Monitoring aus).

---

## 6. Welche Datei macht was

| Datei | Inhalt | Im Repo? |
| --- | --- | --- |
| `deploy/compose.yml` | Alle Dienste, Netze, Volumes, Secrets, Profile | ja |
| `deploy/.env.example` → `.env` | Host-spezifische Werte: Pfade, Domains, Ports, Replikate, Alerting | Beispiel ja, `.env` nein |
| `deploy/secrets/*.txt.example` → `*.txt` | Passwörter und Tokens | Beispiele ja, echte nein |
| `deploy/backend/Dockerfile` | Baut `forge-backend` (Python 3.12, `uv sync --frozen`, non-root) | ja |
| `deploy/nginx/Dockerfile` + `nginx.conf.template` | Baut Frontend und nginx-Image; Template wird beim Start mit den Domains gefüllt | ja |
| `deploy/scripts/*.sh` | Betriebsskripte (siehe Abschnitt 7) | ja |
| `deploy/prometheus/`, `alertmanager/`, `blackbox/`, `loki/`, `alloy/`, `grafana/` | Monitoring-Konfiguration; `*.tmpl` werden von `render-observability-config.sh` nach `/srv/forge/data/runtime/` gerendert | ja |
| `deploy/runbooks/alerts.md` | Für jeden der 37 Alerts: Auswirkung, drei erste Prüfungen, Erholungskriterium, Eskalation | ja |
| `deploy/tests/` | Contract-Tests, die diese Struktur absichern (laufen mit `pytest` im Devcontainer) | ja |
| `/srv/forge/data/` | Alle Laufzeitdaten des Hosts | nein (Host) |

Die Backend-Umgebungsvariablen (was `web` bekommt) stehen zentral im Block
`x-backend-environment` in `compose.yml`; eine Tabelle mit Bedeutung ist in
[`architektur.md`](architektur.md), Abschnitt Settings.

---

## 7. Der Deploy-Ablauf, Schritt für Schritt

`./scripts/deploy.sh` macht in dieser Reihenfolge:

1. **Operation-Lock** (`/srv/forge/data/run/operations.lock`, per `flock`):
   verhindert, dass zwei Operatoren gleichzeitig deployen oder restoren.
2. **Preflight** (`validate-config.sh`): Werkzeuge, Docker-Zugriff,
   Gruppenmitgliedschaft, Domains, Compose-Syntax, TLS-Paar und -Ablauf,
   Verzeichnisse mit Eigentümern und freiem Platz, Secrets, keine Host-Ports
   auf Datenbanken. Bricht mit einer klaren Meldung ab, bevor irgendetwas
   geändert wird.
3. **Images bauen** (`compose build`).
4. **Postgres starten und Passwort prüfen** (ein kurzer `psql select 1` im
   Backup-Container). Fängt den Fall, dass die Datenbank mit einem anderen
   Passwort initialisiert wurde.
5. **Wartungsmodus an** (`maintenance.sh start deploy 3600`): legt die
   Flag-Datei an (nginx zeigt die Wartungsseite), eine *Lease* mit Token, und
   schreibt Metriken (`forge_maintenance_mode 1`, Frist 1 h), die Prometheus
   über den node-exporter liest. Der Alert `ForgeMaintenanceActive` feuert
   und **inhibiert** alle wartungssensitiven Alerts (Postgres down, Probe
   down, …), damit niemand während eines geplanten Deploys angerufen wird.
   Läuft die Frist ab, ohne dass `finish` kam, feuert
   `ForgeMaintenanceOverrun` – kritisch, immer zugestellt.
6. **Backup** (`--profile backup run --rm backup`). Vor jeder Migration.
7. **Migrationen** (`django-migrate`).
8. **Suchindex** neu aufbauen (`search-index`).
9. **Dienste starten** (`compose up -d --scale web=2 --scale celery-worker=1`).
   Compose ersetzt nur Container, deren Image oder Konfiguration sich
   geändert hat.
10. **Health**: nginx `/nginx-healthz`, `web` live und ready, dann die
    öffentliche GraphQL-Probe durch nginx.
11. **Deployment-Metrik** (`forge_deployment_timestamp_seconds{revision}`):
    erscheint in Grafana als vertikale Linie „Deploy revision".
12. **Wartungsmodus aus** (`maintenance.sh finish deploy <token>`), Lease
    weg, Flag weg; die Metrik hält die Alert-Unterdrückung noch 10 Minuten.
13. **Django-Cache leeren** (best effort).

**Wenn ein Schritt fehlschlägt**, bleibt der Zustand stehen, wie er ist:
vor Schritt 5 ist nichts passiert; ab Schritt 5 bleibt der Wartungsmodus
an, das Skript druckt den exakten `finish`-Befehl mit Token. Nach der
Korrektur einfach `./scripts/deploy.sh` erneut starten: dieselbe Lease
(gleicher Grund „deploy") wird fortgesetzt. Nur wenn die Ursache vor den
Migrationen lag, darf `SKIP_BACKUP=true` das Backup überspringen.

`./scripts/maintenance.sh status` zeigt jederzeit Flag, Lease, Token und
Lock. `CONFIRM_RESET_ALL_LEASES=true ./scripts/maintenance.sh reset-all`
räumt verwaisten Zustand auf, verweigert aber, solange ein Lock gehalten
wird.

`start-ops.sh` und `start-all.sh` starten Dienste *ohne* Deploy (kein
Backup, keine Migration): sie rendern die Monitoring-Templates, validieren
sie mit den Original-Werkzeugen (promtool, amtool, loki, alloy, blackbox)
und erzeugen die Monitoring-Container neu, damit geänderte Konfiguration
greift. Kurze Monitoring-Unterbrechung, sonst harmlos.

---

## 8. Alerts lesen

Jeder Alert trägt Labels, die seinen Weg bestimmen:

- `severity`: `info` (nur Dashboard), `warning`, `critical`.
- `notification_scope`: `always`, `business_hours`, `none`.
- `service` und `alert_family`: für Gruppierung und Inhibition (ein
  kritischer Alert unterdrückt die Warnung derselben Familie für dieselbe
  Ressource).
- `maintenance_sensitive: true`: wird während des Wartungsmodus unterdrückt.
- `root_cause: true` + `dependency` (Postgres/Redis down): unterdrückt
  Folgesymptome.

Jede Benachrichtigung enthält `summary`, `impact`, `first_action`, einen
Link ins passende Dashboard und einen Link auf den Abschnitt in
`deploy/runbooks/alerts.md`. Das Runbook ist die erste Anlaufstelle: drei
Prüfungen, Erholungskriterium, Eskalation.

Schwellwerte (Auszug): Probe 2 min down → kritisch; TLS-Ablauf < 30 Tage
Warnung, < 7 Tage kritisch; GraphQL-Serverfehler ≥ 3 in 10 min Warnung,
≥ 10 kritisch; p95-Latenz > 1 s Warnung, > 3 s kritisch; Platte < 15 %
Warnung, < 5 % kritisch; Backup > 26 h Warnung, > 50 h kritisch.

Benachrichtigungsweg testen: `CONFIRM_ALERT_NOTIFICATION_TEST=true
./scripts/send-test-alert.sh` schickt einen Test-Alert und löst ihn nach
5 s wieder auf.

---

## 9. Backup und Wiederherstellung

**Was gesichert wird**: die PostgreSQL-Datenbank (alle Projekte, Kosten,
Stundensätze, Benutzer, Bexio-Spiegel). **Was nicht**: Redis (Cache/Queue,
flüchtig), Meilisearch (aus der DB neu aufbaubar), Prometheus/Loki/Grafana-
Daten (Betriebsdaten), die Konfiguration (`.env`, Secrets, TLS – diese
gehören in einen Passwort-Manager oder Tresor!).

**Wo**: `/srv/forge/data/backups/<ZEIT>/` und eine Kopie in `BACKUP_SHARE`.
`BACKUP_SHARE` sollte ein *anderer* Datenträger sein (NAS, USB-Platte),
sonst ist es kein Backup gegen Plattenausfall.

**Wann**: bei jedem Deploy automatisch, sonst per cron (README, Abschnitt
Backups). Prüfung: monatlich `restore-verify` laufen lassen (README
„Restore-Verification"); Alerts erinnern daran.

**Notfall** (Datenbank kaputt): `./scripts/compose.sh stop web celery-worker
celery-beat`, dann `CONFIRM_RESTORE_POSTGRES=true ./scripts/restore-postgres.sh
<Backup-Ordner>`. Das Skript prüft Checksummen, setzt Wartungsmodus, ersetzt
das Schema und spielt den Dump ein; danach `./scripts/compose.sh up -d` und
den vom Skript genannten `maintenance.sh finish`-Befehl.

**Host-Verlust**: neuer Host, Schritte aus `start_prod.md`, Konfiguration
aus dem Tresor, Restore aus dem Share. Die Git-Revision im
`manifest.txt` sagt, welcher Code-Stand zum Backup gehört.

---

## 10. Betriebsalltag

| Aufgabe | Befehl (in `deploy/`) |
| --- | --- |
| Neue Version ausrollen | `git pull && ./scripts/validate-config.sh && ./scripts/deploy.sh` |
| Nur Monitoring neu starten | `./scripts/start-ops.sh` |
| Status aller Container | `./scripts/compose.sh ps` |
| Logs | `./scripts/compose.sh logs --tail=200 web celery-worker nginx` (Loki/Grafana für Suche) |
| Wartungs-/Lock-Zustand | `./scripts/maintenance.sh status` |
| Backup jetzt | `./scripts/compose.sh --profile backup run --rm backup` |
| Django-Shell | `./scripts/compose.sh exec web python manage.py shell` |
| Benutzer anlegen | Django-Admin unter `/admin/` oder `manage.py createsuperuser` |
| Zertifikat tauschen | Dateien ersetzen, `validate-config.sh`, `compose.sh up -d nginx` |
| Mehr Last | `.env`: `WEB_REPLICAS=3`, dann `deploy.sh` (oder `compose.sh up -d --scale web=3`) |
| Platz schaffen | `docker image prune -f` (alte Images), Backups-Retention greift automatisch |
| Host-Reboot | Alle Dienste haben `restart: unless-stopped` und kommen von selbst wieder |

Was du **nie** tun solltest: `docker compose down` mit einem Profil (nimmt
die Kern-Dienste mit), `docker compose down -v` (löscht Volumes), die
Flag-Datei oder die Lease per Hand löschen, Secrets in Chats/Logs/Tickets
einfügen, `/srv/forge/data/postgres` löschen.

---

## 11. Fehlersuche

| Symptom | Wahrscheinliche Ursache | Erster Befehl |
| --- | --- | --- |
| Browser zeigt Wartungsseite | Deploy läuft oder ist hängen geblieben | `./scripts/maintenance.sh status` |
| `preflight failed: …` | Die Meldung sagt genau was fehlt (Gruppe, Rechte, Secret) | README „Verzeichnisse und Eigentümer" |
| nginx `Restarting` | Konfiguration ungültig (z. B. Zertifikat abgelaufen) | `docker logs forge-nginx-1` |
| `web` nicht `healthy` | App startet nicht (Secret fehlt, DB nicht erreichbar) | `./scripts/compose.sh logs web` |
| `password authentication failed` | DB wurde mit anderem Passwort initialisiert | README „PostgreSQL-Passwort stimmt nicht" |
| Alert `ForgePublicProbeDown` | nginx/TLS/DNS-Problem von außen | Dashboard „API", `curl -k https://<APP_DOMAIN>/health/live/` |
| Alert `ForgeBackupStale` | Cron läuft nicht oder Backup schlägt fehl | `./scripts/compose.sh --profile backup run --rm backup` |
| Grafana 502 | Profil `observability` nicht gestartet | `./scripts/start-ops.sh` |
| Container `Exited (1)` | Logs des Containers | `docker logs <name>` |
| Suche liefert nichts | Index leer | `./scripts/compose.sh --profile deployment run --rm --no-deps search-index` |
| Live-Updates fehlen | WebSocket kommt nicht durch nginx | Browser-Konsole; `curl` mit `Upgrade: websocket` muss 101 liefern |

Zur Diagnose helfen immer: `./scripts/compose.sh ps`, `docker logs <name>`,
Grafana → Overview → „Dependency quick scan" und „Error logs by Compose service".

---

## 12. Was der Testlauf auf dem Raspberry Pi gezeigt hat

Alles davon ist im Repo behoben; hier steht es, damit du die Muster erkennst:

- **16-KB-Speicherseiten** (Pi 5): nginx verlangt für seine Shared-Memory-Zone
  ein Vielfaches der Seitengröße; 64k reichte nicht. Symptom: nginx in einer
  Restart-Schleife, `zone "forge_web" is too small`.
- **Zertifikat selbstsigniert**: der Blackbox-Exporter prüft TLS streng.
  Lösung: das ausgelieferte Zertifikat wird ihm als CA-Datei mitgegeben.
- **`.local`-Namen**: Container lösen mDNS nicht auf. Lösung: `extra_hosts`
  mit `host-gateway` für die Probe; Browser brauchen `/etc/hosts`.
- **pgAdmin** lehnt Login-Adressen mit `.local`, `.test`, `.example` ab.
- **TLS-Schlüssel** muss für die Deploy-Gruppe lesbar sein, weil der
  Preflight als normaler Benutzer läuft.
- **`compose down` mit Profil** entfernt auch die Kern-Dienste. Deshalb
  räumt das Runbook Verifikations-Container gezielt mit `rm -sf` auf.
- **Pi OS ohne Memory-Cgroups**: Container-RAM-Metriken bleiben leer, bis
  `cgroup_enable=memory cgroup_memory=1` in `/boot/firmware/cmdline.txt` steht.
- **Speicher**: der komplette Stack braucht auf dem Pi rund 2 GB RAM; die
  Image-Builds (Frontend, Python-Abhängigkeiten) dauern dort einige Minuten.

Unterschiede Testserver ↔ Kunde: beim Kunden echte DNS-Namen und möglichst
ein CA-Zertifikat (dann HSTS an), `BACKUP_SHARE` auf einem zweiten
Datenträger, SMTP für Alerts konfiguriert, Bexio-Token gesetzt.

---

## 13. Wie das Setup abgesichert ist

Die Struktur ist durch Tests festgeschrieben, die im Devcontainer mit
`pytest deploy/tests` laufen (rund 230 Tests): Compose-Verträge (Service-
Menge, Profile, Ports, Secrets, Replikate), nginx-Template, Images,
Skripte (Preflight mit simulierter Umgebung, Lock, Wartungsmodus, Deploy-
Reihenfolge, Backup-Metriken), Alert-Katalog inklusive Runbook-Abgleich,
Alertmanager-Routen, Grafana-Dashboards (Generator-Check). Die Prometheus-
Regeln haben eigene Unit-Tests (`promtool test rules`, Befehl im README).
Wer `compose.yml` ändert, ohne die Tests anzupassen, bekommt das im
Commit-Hook gemeldet.

---

## 14. Glossar der Metriknamen, die dir begegnen

| Name | Quelle | Bedeutung |
| --- | --- | --- |
| `forge_api_requests_total`, `forge_api_request_duration_seconds` | web | HTTP-Anfragen je API (`graphql`, `auth`) mit Status und Dauer |
| `graphql_requests_total`, `graphql_errors_total`, `graphql_request_duration_seconds` | web (GeneralManager) | GraphQL-Operationen, Fehlercodes, Latenz |
| `forge_celery_queue_depth`, `forge_celery_oldest_task_age_seconds` | Pushgateway (Beat-Task, 60 s) | Wartende Jobs und Alter des ältesten |
| `celery_*` | celery-exporter | Worker, Task-Erfolge/Fehler, Laufzeiten |
| `probe_success`, `probe_ssl_earliest_cert_expiry` | blackbox | Außenprüfung und Zertifikatsablauf |
| `forge_maintenance_mode`, `forge_maintenance_suppress_until_timestamp_seconds` | node-exporter (Textdatei) | Wartungsmodus und Frist |
| `forge_deployment_timestamp_seconds{revision}` | node-exporter (Textdatei) | Zeitpunkt und Git-Revision des letzten Deploys |
| `backup_*`, `restore_verification_*` | Pushgateway | Letztes Backup / letzte Verifikation |
| `up{job=…}` | Prometheus | Ist das Scrape-Ziel erreichbar (1) oder nicht (0) |
