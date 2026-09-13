# Forge Deploy-Runbook (Docker Compose, Single-Host)

Dieses Runbook ist die Referenz für den Betrieb des Forge-Compose-Stacks auf
einem einzelnen Linux-Host. Aufbau und Skripte folgen dem Muster eines ähnlichen Projekts
(ADR 006): nginx als einziger Host-Port, zwei Daphne-Instanzen, Celery,
PostgreSQL hinter pgBouncer, Redis, Meilisearch, dazu die Profile
`observability`, `administration`, `backup` und `restore-verification`.

## Host-Voraussetzungen

Docker Engine mit Compose-Plugin (v2), `git`, `openssl`, `rsync`, `flock`,
`getent` und eine POSIX-Shell. Mindestens 8 GB RAM und 20 GB freier Platz.
Der Host stellt persistente Verzeichnisse für `${DATA_ROOT}`,
`${BACKUP_SHARE}` und die TLS-Dateien bereit. Nur nginx publiziert Host-Ports;
PostgreSQL, pgBouncer, Redis, Meilisearch, Grafana und pgAdmin bleiben in
internen Compose-Netzen.

Der Operator-Account braucht Docker-Zugriff ohne `sudo` (`docker info`).

### Deploy-Gruppe

`.env` und `secrets/*.txt` sind gruppenprivat (`0640`). Die Gruppe aus
`DEPLOY_GROUP` wird beim Start aufgelöst und als Zusatz-GID in alle Container
gereicht, die Secrets lesen. Einmalig pro Host, für jeden Operator wiederholen:

```bash
sudo groupadd --force forge-deploy
sudo usermod -aG forge-deploy "$USER"
```

Nach der Gruppenänderung eine neue Login-Sitzung starten; eine bestehende Shell
bekommt die Gruppe nicht.

### Verzeichnisse und Eigentümer

Die Container laufen mit festen UIDs: Backend `1000:1000`, Prometheus,
Alertmanager und Pushgateway `65534:65534`, Grafana `472:0`, Loki
`10001:10001`, pgAdmin `5050:5050`. Der Preflight prüft genau diese Eigentümer
und Modi; er repariert nichts.

```bash
sudo mkdir -p /srv/forge/data/{postgres,redis,meilisearch,static,run,runtime/node-exporter,backups,celerybeat,alertmanager,prometheus,grafana,loki,alloy,pushgateway,pgadmin,restore-verification/files} /srv/forge/backup-share /etc/forge/tls
sudo chown -R 1000:1000 /srv/forge/data/{static,backups,celerybeat,restore-verification} /srv/forge/backup-share
sudo chmod 0755 /srv/forge/data/static
sudo chmod 0750 /srv/forge/data/{backups,celerybeat,restore-verification} /srv/forge/backup-share
sudo chown 65534:65534 /srv/forge/data/{alertmanager,prometheus,pushgateway}
sudo chmod 0750 /srv/forge/data/{alertmanager,prometheus,pushgateway}
sudo chown 472:0 /srv/forge/data/grafana && sudo chmod 0750 /srv/forge/data/grafana
sudo chown 10001:10001 /srv/forge/data/loki && sudo chmod 0750 /srv/forge/data/loki
sudo chown 5050:5050 /srv/forge/data/pgadmin && sudo chmod 0750 /srv/forge/data/pgadmin
sudo chgrp forge-deploy /srv/forge/data/{run,runtime} && sudo chmod 2770 /srv/forge/data/{run,runtime}
sudo chgrp forge-deploy /srv/forge/data/runtime/node-exporter && sudo chmod 2775 /srv/forge/data/runtime/node-exporter
```

`postgres`, `redis`, `meilisearch` und `alloy` setzen ihre Eigentümer beim
ersten Start selbst. `run` und `runtime` gehören der Deploy-Gruppe: dort liegen
Operation-Lock, Maintenance-Flag, Lease und die Textfile-Metriken für den
node-exporter (`runtime/node-exporter`, im Container read-only).

## TLS-Zertifikat

nginx bedient drei Hostnamen über ein Zertifikat: `APP_DOMAIN`,
`MONITORING_DOMAIN` (Grafana) und `ADMIN_DOMAIN` (pgAdmin). Das Zertifikat muss
alle drei als Subject Alternative Names enthalten. Für Test- und
Intranet-Betrieb genügt ein selbstsigniertes Zertifikat:

```bash
sudo openssl req -x509 -nodes -newkey rsa:4096 -sha256 -days 3650 \
  -keyout /etc/forge/tls/privkey.pem \
  -out /etc/forge/tls/fullchain.pem \
  -subj "/CN=forge.example.local" \
  -addext "subjectAltName=DNS:forge.example.local,DNS:monitoring.forge.example.local,DNS:db.forge.example.local"
sudo chgrp forge-deploy /etc/forge/tls/privkey.pem
sudo chmod 0640 /etc/forge/tls/privkey.pem
sudo chmod 0644 /etc/forge/tls/fullchain.pem
```

Der private Schlüssel gehört wie die Secrets der Deploy-Gruppe (`0640`): der
Preflight läuft als Operator und prüft Ablauf und Schlüssel-Zuordnung (RSA und
EC); nginx liest beide Dateien im Container als root. HSTS ist bewusst aus,
damit Browser selbstsignierte Zertifikate weiterhin akzeptieren; mit einem
CA-Zertifikat `DJANGO_SECURE_HSTS_SECONDS=31536000` in `.env` setzen.

### DNS

Alle drei Namen müssen auf den Host zeigen (interner DNS oder `/etc/hosts` auf
den Clients). mDNS (`.local`) löst keine Subdomains auf; für Tests auf den
Clients eintragen (der Blackbox-Exporter erreicht `APP_DOMAIN` unabhängig davon
über `host-gateway`):

```text
192.168.1.10 forge.example.local monitoring.forge.example.local db.forge.example.local
```

## Konfiguration

Aus `deploy/`:

```bash
cp .env.example .env
for file in secrets/*.txt.example; do cp "$file" "${file%.example}"; done
```

`.env`: Domains, Pfade, Ports, Replikate, Alerting. Kein `DEPLOY_GROUP_GID`
eintragen; die GID wird zur Laufzeit aufgelöst. Bei einem HTTPS-Port ungleich
443 zusätzlich `CSRF_TRUSTED_ORIGINS=https://<domain>:<port>` setzen.

Secrets erzeugen (nie in Logs oder Chats einfügen):

```bash
umask 077
for name in django_secret_key postgres_password meilisearch_api_key grafana_admin_password pgadmin_password; do
  openssl rand -base64 48 | tr -d '\n' > "secrets/$name.txt"
done
printf 'admin:%s\n' "$(openssl passwd -apr1)" > secrets/admin_htpasswd.txt   # fragt das Passwort ab
sudo chgrp forge-deploy .env secrets/*.txt
sudo chmod 0640 .env secrets/*.txt
```

| Secret | Pflicht | Hinweis |
| --- | --- | --- |
| `django_secret_key.txt` | ja | mindestens 50 Zeichen |
| `postgres_password.txt` | ja | initialisiert die Datenbank beim ersten Start |
| `meilisearch_api_key.txt` | ja | Master-Key von Meilisearch |
| `admin_htpasswd.txt` | ja | Basic-Auth vor pgAdmin (`user:hash`, apr1 oder bcrypt) |
| `grafana_admin_password.txt` | ja | Grafana-Admin |
| `pgadmin_password.txt` | ja | Login mit `PGADMIN_DEFAULT_EMAIL` |
| `bexio_access_token.txt` | nein | leer = Bexio-Dev-Modus mit Fixture-Daten (Preflight warnt) |
| `teams_workflow_url.txt` | nein | nur bei `ALERT_TEAMS_ENABLED=true`, sonst leer |
| `smtp_password.txt` | nein | nur bei `ALERT_SMTP_AUTH_ENABLED=true` (`ALERT_SMTP_PASSWORD_FILE`) |

Compose-Befehle immer über `./scripts/compose.sh` (lädt `ENV_FILE`, löst die
Deploy-Gruppe auf), nie direkt über `docker compose`:

```bash
./scripts/compose.sh config --quiet
./scripts/compose.sh --profile observability config --quiet
./scripts/compose.sh ps
```

## Erst-Deployment

```bash
cd deploy
./scripts/validate-config.sh
./scripts/deploy.sh
./scripts/start-ops.sh
```

`deploy.sh` nimmt den Operation-Lock, validiert, baut die Images, startet
PostgreSQL und prüft das Passwort, aktiviert den Wartungsmodus (Lease mit
Token), sichert die Datenbank, migriert (`check --deploy`, `migrate`,
`collectstatic`, `create_groups`), baut die Suchindizes neu, startet die
Kern-Dienste mit `WEB_REPLICAS` (Default 2) und `CELERY_REPLICAS`, prüft
nginx-, Liveness-, Readiness- und GraphQL-Probe, veröffentlicht die
Deployment-Metrik, beendet den Wartungsmodus und leert den Django-Cache.
`SOURCE_REVISION` kommt aus dem Git-Checkout, wenn `.env` `unknown` enthält.

Ein fehlgeschlagener Index-Neuaufbau bricht das Deployment ab und lässt den
Wartungsmodus aktiv.

Ersten Admin anlegen:

```bash
./scripts/compose.sh exec web python manage.py createsuperuser
```

## Test-Server-Checkliste

1. Revision auschecken und bestätigen:
   ```bash
   git fetch --all --prune && git checkout <commit-or-branch> && git rev-parse --short HEAD
   ```
2. `.env` und Secrets anlegen (siehe Konfiguration).
3. TLS-Zertifikat erzeugen, DNS/`/etc/hosts` setzen.
4. Verzeichnisse mit Eigentümern anlegen (siehe oben) und prüfen:
   `df -h /srv/forge/data /srv/forge/backup-share`.
5. Konfiguration validieren:
   ```bash
   ./scripts/validate-config.sh
   for profile in observability administration backup restore-verification deployment; do
     ./scripts/compose.sh --profile "$profile" config --quiet
   done
   ```
6. Images bauen: `./scripts/compose.sh build`
7. Migrieren, Suchindex aufbauen, Kern starten:
   ```bash
   ./scripts/compose.sh run --rm django-migrate
   ./scripts/compose.sh --profile deployment run --rm --no-deps search-index
   ./scripts/compose.sh up -d --scale web=2 --scale celery-worker=1 web celery-worker celery-beat nginx
   ./scripts/compose.sh ps
   ```
8. Observability und pgAdmin starten: `./scripts/start-ops.sh`
9. HTTP-Smoke-Test:
   ```bash
   curl --fail https://<app-domain>/health/live/
   curl --fail https://<app-domain>/health/ready/
   curl --fail --get --data-urlencode 'query=query HealthProbe { __typename }' --data-urlencode 'operationName=HealthProbe' https://<app-domain>/graphql/
   curl --fail https://<monitoring-domain>/api/health
   curl --fail --user admin https://<admin-domain>/login
   ```
   Plain-HTTP-Anfragen an die drei Domains erhalten `308` auf HTTPS; unbekannte
   Hosts `404`.
10. WebSocket-Smoke-Test: `wss://<app-domain>/graphql/` mit Subprotokoll
    `graphql-transport-ws`; `{"type":"connection_init"}` muss
    `{"type":"connection_ack"}` liefern.
11. Backup laufen lassen und verifizieren (siehe Backups, Restore-Verification).
12. Logs vor der Übergabe prüfen:
    ```bash
    ./scripts/compose.sh logs --tail=200 web celery-worker celery-beat nginx
    ./scripts/compose.sh --profile observability logs --tail=200 prometheus grafana loki
    ```
    Auf `ERROR`, `500`, `DisallowedHost` und unaufgelöste Upstreams achten.

## Routine-Deployment

```bash
cd deploy
git pull
./scripts/validate-config.sh
./scripts/deploy.sh
```

Erfolgreiche Deployments schließen ihre Lease selbst. Ein Fehlschlag lässt die
Lease aktiv und druckt den token-gebundenen Wiederherstellungsbefehl. Den
Wartungsmodus nie durch Löschen von `${DATA_ROOT}/runtime/maintenance`
beenden.

### Retry und Recovery

```bash
./scripts/maintenance.sh status
```

Nennt die aktive Lease denselben Grund wie die geplante Arbeit, das Deployment
(oder den Restore) einfach erneut starten. Nach einem Fehler vor den
Migrationen darf das vorherige Backup wiederverwendet werden:

```bash
SKIP_BACKUP=true ./scripts/deploy.sh
```

Verwaisten Zustand nur nach Bestätigung zurücksetzen, dass keine Operation
läuft (`reset-all` verweigert bei gehaltenem Lock):

```bash
CONFIRM_RESET_ALL_LEASES=true ./scripts/maintenance.sh reset-all
```

### PostgreSQL-Passwort stimmt nicht

Meldet der Precheck `password authentication failed`, wurde
`${DATA_ROOT}/postgres` mit einem anderen Passwort initialisiert als
`secrets/postgres_password.txt`. Rolle im laufenden Container reparieren:

```bash
./scripts/compose.sh exec -T postgres sh -ec 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -v new_password="$(cat /run/secrets/postgres_password)" -c "ALTER USER forge WITH PASSWORD :'\''new_password'\'';"'
```

`${DATA_ROOT}/postgres` nicht löschen, außer die Datenbank ist wegwerfbar.

## Dienste starten ohne Redeploy

```bash
./scripts/start-ops.sh   # Observability + pgAdmin
./scripts/start-all.sh   # Kern + Observability + pgAdmin
```

Beide rendern und validieren zuerst die Observability-Konfiguration
(`render-observability-config.sh`, `validate-observability-config.sh`) und
erzeugen Prometheus, Alertmanager, Grafana, Loki, Alloy und Blackbox-Exporter
neu, damit eingebundene Konfiguration nicht veraltet. Das ist eine kurze
Monitoring-Unterbrechung; für Code-Änderungen `deploy.sh` verwenden.

## Alerting

Alertmanager benachrichtigt per E-Mail (SMTP) und optional Microsoft Teams.
Default in `.env.example`: Teams aus, SMTP ohne Auth und ohne TLS (internes
Relay). Für authentifiziertes SMTP:

```dotenv
ALERT_SMTP_SMARTHOST=smtp.example.local:587
ALERT_SMTP_FROM=forge-alerts@example.local
ALERT_SMTP_AUTH_ENABLED=true
ALERT_SMTP_REQUIRE_TLS=true
ALERT_SMTP_USERNAME=forge-alerts@example.local
ALERT_SMTP_PASSWORD_FILE=./secrets/smtp_password.txt
ALERT_EMAIL_TO=forge-ops@example.local
```

Zustellung bewusst prüfen (sendet einen Test-Alert, wartet, löst ihn auf):

```bash
CONFIRM_ALERT_NOTIFICATION_TEST=true ./scripts/send-test-alert.sh
```

Alerts, Schwellwerte und Erstmaßnahmen: `runbooks/alerts.md`. Der
Wartungsmodus inhibiert wartungssensitive Alerts bis zum Ablauf des
Zeitfensters (`DEPLOY_MAINTENANCE_TIMEOUT_SECONDS`).

## Skalierung

Nur zustandslose Dienste skalieren:

```bash
./scripts/compose.sh up -d --scale web=3 --scale celery-worker=2
```

`django-migrate`, `celery-beat`, `backup` und `restore-verify` bleiben
one-shot bzw. Singleton.

## Backups

Manuell oder per cron/systemd:

```bash
./scripts/compose.sh --profile backup run --rm backup
```

Der Job dumpt PostgreSQL (`pg_dump --format=custom`), prüft den Dump mit
`pg_restore --list`, schreibt `manifest.txt` und `SHA256SUMS`, verschiebt das
Verzeichnis atomar nach `${DATA_ROOT}/backups/<YYYYMMDDTHHMMSSZ>`, kopiert es
nach `${BACKUP_SHARE}` und behält 30 tägliche und 12 monatliche Stände. Metriken
gehen an den Pushgateway (`backup_*`).

Beispiel-Cron (täglich 02:30):

```cron
30 2 * * * cd /srv/forge/app/deploy && ./scripts/compose.sh --profile backup run --rm backup >> /var/log/forge-backup.log 2>&1
```

## Restore-Verification

`RESTORE_BACKUP` in `.env` auf ein Backup-Verzeichnis setzen, dann:

```bash
./scripts/compose.sh --profile restore-verification run --rm restore-verify
```

Das Profil startet ein isoliertes PostgreSQL mit temporärem Volume, prüft die
Checksummen, spielt den Dump ein und lässt `manage.py check` und
`showmigrations --plan` laufen. Produktionsdaten werden nicht berührt.
Cleanup der Verifikationsressourcen:

```bash
./scripts/compose.sh --profile restore-verification down
```

## PostgreSQL-Restore

Stellt nur die Datenbank aus einem Backup-Verzeichnis unterhalb von
`${DATA_ROOT}/backups` oder `${BACKUP_SHARE}` wieder her:

```bash
./scripts/compose.sh stop web celery-worker celery-beat
CONFIRM_RESTORE_POSTGRES=true ./scripts/restore-postgres.sh /srv/forge/backup-share/20260913T020000Z
```

Das Skript prüft `SHA256SUMS`, aktiviert den Wartungsmodus, ersetzt das
`public`-Schema und läuft `pg_restore --no-owner --no-privileges`. Der
Wartungsmodus bleibt aktiv; nach manueller Prüfung den vom Skript gedruckten
`finish`-Befehl ausführen und die Dienste mit `./scripts/compose.sh up -d`
starten.

## Zertifikat-Rotation

Neue Dateien an `TLS_CERT_FILE`/`TLS_KEY_FILE` ablegen, dann:

```bash
./scripts/validate-config.sh
./scripts/compose.sh up -d nginx
```

## Incident-Recovery (Host-Verlust)

1. Neuen Host mit denselben Mounts und DNS-Namen bereitstellen.
2. Git-Revision aus `manifest.txt` des letzten Backups auschecken.
3. `.env`, Secrets und TLS-Dateien aus dem sicheren Speicher wiederherstellen.
4. PostgreSQL aus dem Backup wiederherstellen (siehe oben).
5. `./scripts/validate-config.sh`, `./scripts/deploy.sh`, `./scripts/start-ops.sh`.

Prometheus behält Metriken 45 Tage (10 GB), Loki Logs 7 Tage.

## Entwicklung an der Deploy-Konfiguration

- Contract-Tests (Compose, nginx, Images, Skripte, Alerts, Grafana) laufen im
  Devcontainer über `pytest deploy/tests`; die Profil-Renderings brauchen
  Docker und werden ohne übersprungen.
- Dashboards werden aus `grafana/scripts/dashboard_specs.py` generiert:
  ```bash
  python deploy/grafana/scripts/build_dashboards.py
  python deploy/grafana/scripts/build_dashboards.py --check
  ```
- Prometheus-Unit-Tests (Alerts, Recording-Rules, Grafana-Annotationen):
  ```bash
  docker run --rm -v "$PWD/deploy/prometheus:/rules:ro" --entrypoint /bin/promtool prom/prometheus:v3.12.0 \
    test rules /rules/tests/alerts.test.yml /rules/recording-rules.test.yml /rules/grafana-annotations.test.yml /rules/grafana-curated.test.yml
  ```
- Native Validatoren für die gerenderte Observability-Konfiguration:
  `./scripts/validate-observability-config.sh` (läuft auch in `start-ops.sh`).

## Bekannte Grenzen

- Raspberry Pi 5 (8 GB) trägt den kompletten Stack für Tests; bei
  Speicherdruck `WEB_REPLICAS`, `PROMETHEUS_RETENTION_SIZE` oder das
  Observability-Profil reduzieren.
- Ein kompletter Host-Ausfall ist vom mitlaufenden Stack nicht erkennbar;
  für Produktion einen externen Verfügbarkeits-Check ergänzen.
