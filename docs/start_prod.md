# Produktion starten – Forge

Das Gegenstück zu `start_dev.md`: der kürzeste Weg von einem leeren Linux-Host
zu einer laufenden Forge-Installation. Jeder Befehl hier hat eine ausführliche
Erklärung in [`explain_prod_setup.md`](explain_prod_setup.md); das vollständige
Betriebshandbuch mit allen Sonderfällen ist [`deploy/README.md`](../deploy/README.md).

## 0. Was du brauchst

- Einen Linux-Host (Debian/Ubuntu, x86-64 oder arm64), 8 GB RAM, 20 GB frei.
  Getestet auf einem Raspberry Pi 5.
- Einen Benutzer mit `sudo` und Docker-Zugriff. Docker Engine mit Compose-Plugin:
  ```bash
  sudo apt install -y docker.io docker-compose docker-buildx git openssl rsync
  sudo usermod -aG docker "$USER"   # danach neu anmelden
  ```
- Drei Hostnamen, die auf den Host zeigen (interner DNS oder `/etc/hosts` auf
  den Clients): App, Monitoring, Admin. Beispiel: `forge.firma.local`,
  `monitoring.forge.firma.local`, `db.forge.firma.local`.
  Achtung: `.local`-Namen löst nur der Host selbst per mDNS auf, Subdomains
  davon niemand, deshalb `/etc/hosts` auf jedem Client.
- Optional: den Bexio-API-Token des Kunden. Ohne Token läuft Forge im
  Fixture-Modus (Testdaten statt echter Bexio-Daten).

## 1. Host vorbereiten (einmalig, mit sudo)

Deploy-Gruppe, Datenverzeichnisse mit den richtigen Eigentümern, TLS-Ordner.
Der Block steht in `deploy/README.md` unter „Verzeichnisse und Eigentümer";
hier die Kurzform:

```bash
sudo groupadd --force forge-deploy && sudo usermod -aG forge-deploy "$USER"
sudo mkdir -p /srv/forge/data/{postgres,redis,meilisearch,static,run,runtime/node-exporter,backups,celerybeat,alertmanager,prometheus,grafana,loki,alloy,pushgateway,pgadmin,restore-verification/files} /srv/forge/backup-share /etc/forge/tls /etc/forge/secrets
sudo chgrp forge-deploy /etc/forge/secrets && sudo chmod 2770 /etc/forge/secrets
sudo chown -R 1000:1000 /srv/forge/data/{static,backups,celerybeat,restore-verification} /srv/forge/backup-share
sudo chmod 0755 /srv/forge/data/static
sudo chmod 0750 /srv/forge/data/{backups,celerybeat,restore-verification} /srv/forge/backup-share
sudo chown 65534:65534 /srv/forge/data/{alertmanager,prometheus,pushgateway} && sudo chmod 0750 /srv/forge/data/{alertmanager,prometheus,pushgateway}
sudo chown 472:0 /srv/forge/data/grafana && sudo chmod 0750 /srv/forge/data/grafana
sudo chown 10001:10001 /srv/forge/data/loki && sudo chmod 0750 /srv/forge/data/loki
sudo chown 5050:5050 /srv/forge/data/pgadmin && sudo chmod 0750 /srv/forge/data/pgadmin
sudo chgrp forge-deploy /srv/forge/data/{run,runtime} && sudo chmod 2770 /srv/forge/data/{run,runtime}
sudo chgrp forge-deploy /srv/forge/data/runtime/node-exporter && sudo chmod 2775 /srv/forge/data/runtime/node-exporter
```

Danach **neu anmelden** (die Gruppe gilt erst in einer neuen Sitzung).
Derselbe Block als Skript, inklusive Zertifikat (Schritt 2), SSH nur mit
Schlüssel und automatischen Sicherheitsupdates:
`sudo OPERATOR=$USER APP_DOMAIN=forge.firma.local sh deploy/scripts/host-prep.sh`.

## 2. TLS-Zertifikat

Ein Zertifikat für alle drei Namen. Selbstsigniert reicht im Intranet
(Browser zeigen einmalig eine Warnung), ein Zertifikat der Firmen-CA ist besser:

```bash
sudo openssl req -x509 -nodes -newkey rsa:4096 -sha256 -days 3650 \
  -keyout /etc/forge/tls/privkey.pem -out /etc/forge/tls/fullchain.pem \
  -subj "/CN=forge.firma.local" \
  -addext "subjectAltName=DNS:forge.firma.local,DNS:monitoring.forge.firma.local,DNS:db.forge.firma.local"
sudo chgrp forge-deploy /etc/forge/tls/privkey.pem
sudo chmod 0640 /etc/forge/tls/privkey.pem
sudo chmod 0644 /etc/forge/tls/fullchain.pem
```

## 3. Repository holen

```bash
git clone https://github.com/EliasBauer/Forge.git ~/forge
cd ~/forge/deploy
```

Der Ordner `deploy/` ist ab jetzt dein Arbeitsverzeichnis. Alle Skripte
liegen unter `deploy/scripts/`.

## 4. Konfiguration und Secrets

```bash
cp .env.example .env
```

In `.env` anpassen: `APP_DOMAIN`, `MONITORING_DOMAIN`, `ADMIN_DOMAIN`,
`CSRF_TRUSTED_ORIGINS` (= `https://<APP_DOMAIN>`), `PGADMIN_DEFAULT_EMAIL`
(keine `.local`-Adresse), `SECRETS_DIR=/etc/forge/secrets`, bei Bedarf
Alerting (SMTP). `DATA_ROOT`, `BACKUP_SHARE` und die TLS-Pfade passen zu
Schritt 1 und 2.

Die Secrets liegen in `SECRETS_DIR`, also außerhalb des Checkouts: ein
`git clean` oder ein neuer Clone kann sie nicht löschen. Vier Werte wählst
du selbst und trägst sie in eine Datei ein (nie in Chats oder Logs einfügen):

```bash
umask 027
cat > /etc/forge/secrets/forge-secrets.env <<'EOT'
ADMIN_BASIC_AUTH_PASSWORD=DEIN-PASSWORT
GRAFANA_ADMIN_PASSWORD=DEIN-PASSWORT
PGADMIN_PASSWORD=DEIN-PASSWORT
BEXIO_ACCESS_TOKEN=DEIN-BEXIO-TOKEN
EOT
./scripts/secrets-from-env.sh
sudo chgrp forge-deploy .env && sudo chmod 0640 .env
```

Den Rest (Django-Key, Postgres, Meilisearch) erzeugt das Skript zufällig.
Läuft das Bexio-Token ab: neuen Wert eintragen, Skript erneut ausführen,
danach `./scripts/compose.sh up -d --force-recreate web celery-worker celery-beat`.

`teams_workflow_url.txt` und `smtp_password.txt` bleiben leer, solange Teams
und SMTP-Auth in `.env` aus sind. Die Werte in `grafana_admin_password.txt`,
`pgadmin_password.txt` und das htpasswd-Passwort brauchst du später zum
Einloggen; bewahre sie im Passwort-Manager auf.

## 5. Prüfen und deployen

```bash
./scripts/validate-config.sh     # Preflight: Tools, Gruppe, Verzeichnisse, TLS, Secrets
./scripts/deploy.sh              # baut Images, sichert, migriert, startet, prüft Health
./scripts/start-ops.sh           # Monitoring (Grafana, Prometheus, Loki, …) und pgAdmin
./scripts/compose.sh ps          # alle Container mit Status
```

Der erste `deploy.sh` dauert einige Minuten (Image-Build). Bricht er ab,
bleibt der Wartungsmodus an; `./scripts/maintenance.sh status` zeigt den
Zustand, nach der Korrektur einfach `./scripts/deploy.sh` erneut ausführen.

## 6. Ersten Benutzer anlegen

```bash
./scripts/compose.sh exec web python manage.py createsuperuser
```

Der Superuser kann sich unter `https://<APP_DOMAIN>/` anmelden und im
Django-Admin (`/admin/`) weitere Benutzer anlegen und den Gruppen `Admin`,
`Projektleiter`, `Betrachter`, `Monteur` zuordnen (die Gruppen legt das
Deployment automatisch an).

## 7. Kurz-Check

| Was | Wo | Erwartung |
| --- | --- | --- |
| App | `https://<APP_DOMAIN>/` | Login-Seite |
| Health | `https://<APP_DOMAIN>/health/ready/` | `{"status": "ok", …}` |
| Grafana | `https://<MONITORING_DOMAIN>/` | Login `admin` + `grafana_admin_password.txt`, Ordner Operations/Curated/Exporters |
| pgAdmin | `https://<ADMIN_DOMAIN>/` | erst Basic-Auth (htpasswd), dann pgAdmin-Login mit `PGADMIN_DEFAULT_EMAIL` + `pgadmin_password.txt` |
| Alerts | Grafana → Dashboard „Forge Overview" → Panel „Firing alerts" | 0 |

## 8. Alltag

```bash
cd ~/forge/deploy
git pull && ./scripts/validate-config.sh && ./scripts/deploy.sh   # Update einspielen
./scripts/compose.sh --profile backup run --rm backup             # Backup (auch per cron)
./scripts/compose.sh logs --tail=200 web celery-worker nginx      # Logs
./scripts/maintenance.sh status                                   # Wartungs-/Lock-Zustand
```

Backup täglich per cron (siehe `deploy/README.md`, Abschnitt Backups), und
mindestens monatlich eine Restore-Verification laufen lassen.

Alles Weitere, insbesondere *warum* die Dinge so gebaut sind und was bei
Störungen zu tun ist: [`explain_prod_setup.md`](explain_prod_setup.md).
