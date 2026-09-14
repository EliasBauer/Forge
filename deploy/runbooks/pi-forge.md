# Runbook: Raspberry Pi „forge" neu aufsetzen

Ziel: `elias_admin@forge.local` (Raspberry Pi 5) von der leeren SD-Karte bis
zum laufenden Forge-Stack von `main`, mit getestetem Backup. Jeder Befehl mit
dem Grund dahinter. Die allgemeine Kurzanleitung ist
[`docs/start_prod.md`](../../docs/start_prod.md); hier steht nur, was auf dem
Pi konkret passiert. Stand: 2026-09-14, Neuaufsetzen Nr. 2.

## 1. SD-Karte flashen (am Mac, Raspberry Pi Imager)

- Gerät: Raspberry Pi 5. Betriebssystem: **Raspberry Pi OS Lite (64-bit)**,
  Debian 13 „trixie". Lite, weil kein Desktop gebraucht wird und der Pi den
  RAM für den Stack braucht (rund 2 GB).
- Anpassungen im Imager (Zahnrad / „Einstellungen bearbeiten"):
  - Hostname `forge` → mDNS-Name `forge.local`.
  - Benutzer `elias_admin`, Passwort setzen (nur für `sudo`, nicht für SSH).
  - SSH aktivieren, **nur Public-Key-Authentifizierung**, den öffentlichen
    Schlüssel vom Mac eintragen (`cat ~/.ssh/id_ed25519.pub`).
  - WLAN nicht konfigurieren, der Pi hängt per Kabel am Router.
  - Zeitzone `Europe/Zurich`, Tastatur egal (kein Bildschirm).
- Karte in den Pi, Strom dran, etwa zwei Minuten warten.

## 2. Erster Login und Grundpakete

```bash
ssh-keygen -R forge.local      # alten Host-Key vom vorigen Pi vergessen, sonst warnt SSH
ssh elias_admin@forge.local
```

Auf dem Pi:

```bash
sudo apt update && sudo apt full-upgrade -y                      # aktueller Stand, danach ggf. reboot
sudo apt install -y docker.io docker-compose docker-buildx git openssl rsync
```

`docker.io` und `docker-compose` (v2) kommen aus Debian; die Version dort
(Compose 2.26) reicht, verschachtelte Variablen wie `${SECRETS_DIR:-./secrets}`
funktionieren damit. `rsync` braucht das Backup zum Spiegeln auf `BACKUP_SHARE`.

## 3. Host vorbereiten (root)

Das Skript liegt im Repo, also erst klonen, dann als root ausführen:

```bash
git clone https://github.com/EliasBauer/Forge.git ~/forge
sudo OPERATOR=elias_admin APP_DOMAIN=forge.local sh ~/forge/deploy/scripts/host-prep.sh
```

Was es tut, und warum:

- Gruppe `forge-deploy` und `elias_admin` hinein: nur diese Gruppe darf `.env`,
  Secrets und den TLS-Schlüssel lesen. Dazu `elias_admin` in `docker`.
- `/srv/forge/data/...` mit den festen Container-UIDs (Backend 1000,
  Prometheus 65534, Grafana 472, Loki 10001, pgAdmin 5050). Der Preflight
  prüft genau diese Eigentümer und repariert nichts.
- `/etc/forge/secrets` (2770, Gruppe `forge-deploy`, Operatoren schreiben ohne root): Secrets liegen
  außerhalb des Checkouts, `SECRETS_DIR` in `.env` zeigt dorthin.
- Selbstsigniertes Zertifikat für `forge.local`,
  `monitoring.forge.local`, `db.forge.local`. Bewusst **ohne IP**
  im SAN: die IP kommt per DHCP und darf sich ändern, die Namen nicht.
- SSH: Passwort-Login und Root-Login aus (nur wenn ein Schlüssel hinterlegt ist).
- `unattended-upgrades`: Debian-Sicherheitsupdates laufen nachts automatisch.

Danach **ausloggen und neu einloggen**, sonst gelten die Gruppen nicht.

Nur auf dem Pi zusätzlich, weil `forge.local` über mDNS aufgelöst wird:

```bash
sudo sed -i 's/^use-ipv6=yes/use-ipv6=no/' /etc/avahi/avahi-daemon.conf && sudo systemctl restart avahi-daemon
```

Avahi nennt sonst auch die IPv6-Adresse vom Provider; Browser probieren die
zuerst und hängen, wenn sie sich ändert oder gefiltert wird.

## 4. Konfiguration und Secrets

Einmal von root (`chmod 2770`) ist im Skript inzwischen enthalten; hier
brauchte es das noch nachträglich. Alles Weitere läuft als `elias_admin`.

`.env` aus der Vorlage, nur die serverindividuellen Werte geändert:

```bash
cd ~/forge/deploy && cp .env.example .env
sed -i -e 's|^SECRETS_DIR=.*|SECRETS_DIR=/etc/forge/secrets|' \
       -e 's|^APP_DOMAIN=.*|APP_DOMAIN=forge.local|' \
       -e 's|^MONITORING_DOMAIN=.*|MONITORING_DOMAIN=monitoring.forge.local|' \
       -e 's|^ADMIN_DOMAIN=.*|ADMIN_DOMAIN=db.forge.local|' \
       -e 's|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://forge.local|' \
       -e 's|^APP_HOST_ALIASES=.*|APP_HOST_ALIASES=localhost,127.0.0.1,forge|' .env
chgrp forge-deploy .env && chmod 0640 .env
```

- `SECRETS_DIR=/etc/forge/secrets`: Secrets außerhalb des Checkouts.
- Die drei Domains sind die Namen im Zertifikat; `CSRF_TRUSTED_ORIGINS` muss
  zur App-Domain passen, sonst lehnt Django Formulare und Logins ab.
- `APP_HOST_ALIASES` erweitert `ALLOWED_HOSTS` um den nackten Hostnamen, damit
  auch `http://forge` aus dem LAN nicht mit „Bad Request" endet.
- `0640` + Gruppe: Preflight verlangt, dass `.env` weder weltlesbar noch
  nur für den Eigentümer lesbar ist (die Container lesen sie über die Gruppe).

Die vier gewählten Werte stehen in `/etc/forge/secrets/forge-secrets.env`
(root, `0640`, Gruppe `forge-deploy`, Abschnitt 3). Daraus die Dateien:

```bash
./scripts/secrets-from-env.sh          # schreibt 9 Dateien nach /etc/forge/secrets
./scripts/validate-config.sh           # Preflight, erwartet: „preflight ok"
```

Was dabei entsteht: `admin_htpasswd.txt` (Basic-Auth-Passwort als apr1-Hash,
Benutzer `admin`), `grafana_admin_password.txt`, `pgadmin_password.txt`,
`bexio_access_token.txt` aus deiner Datei; `django_secret_key.txt`,
`postgres_password.txt`, `meilisearch_api_key.txt` zufällig (64 Zeichen, werden
bei späteren Läufen nicht überschrieben); `teams_workflow_url.txt` und
`smtp_password.txt` leer, weil Teams und SMTP-Auth in `.env` aus sind.

**Bexio-Token erneuern** (läuft etwa alle zwei Monate ab): neuen Wert in
`forge-secrets.env` eintragen, dann

```bash
cd ~/forge/deploy && ./scripts/secrets-from-env.sh && ./scripts/compose.sh up -d --force-recreate web celery-worker celery-beat
```

Kein Build, keine Migration, keine Wartungspause. Die Container lesen die
Datei beim Start, darum das Neu-Erzeugen.

## 5. Deploy

```bash
cd ~/forge/deploy
nohup ./scripts/deploy.sh > ~/forge-deploy.log 2>&1 &     # ca. 20 Minuten beim ersten Mal
./scripts/start-ops.sh > ~/forge-start-ops.log 2>&1       # Monitoring + pgAdmin, danach
```

`nohup … &`, weil der erste Lauf die Images baut (Frontend, Python-Wheels
auf arm64) und eine abgebrochene SSH-Sitzung den Deploy sonst mitreißt.
Fortschritt: `grep -v '^{' ~/forge-deploy.log | tail` (die JSON-Zeilen sind
Django-Logs). Fertig ist er, wenn `deploy.sh` nicht mehr in `ps` steht und
`./scripts/maintenance.sh status` keinen aktiven Wartungsmodus zeigt.

Was `deploy.sh` der Reihe nach tut: Preflight, Images bauen, Postgres hochfahren
und Passwort prüfen, Wartungsmodus an, **Backup** (beim ersten Lauf leer),
Migrationen, Suchindex, alle Kern-Container starten, Health-Checks
(`/nginx-healthz`, `/health/live/`, `/health/ready/`, GraphQL), Wartungsmodus
aus, Cache leeren. Bricht ein Schritt ab, bleibt der Wartungsmodus an; nach der
Korrektur einfach `deploy.sh` erneut ausführen.

Kontrolle danach:

```bash
./scripts/compose.sh ps                                                   # alles healthy
curl -sk -H 'Host: forge.local' https://127.0.0.1/health/ready/           # {"status": "ok", …}
./scripts/compose.sh exec -T web python manage.py showmigrations --plan | grep -c '\[ \]'   # 0 offen
```

Ergebnis am 2026-09-14: 35 Migrationen angewendet, 0 offen, neun Kern-Container
healthy, Celery Beat schickt die Queue-Metriken minütlich.

Auf jedem Client, der Grafana oder pgAdmin erreichen soll: mDNS löst keine
Subdomains auf, darum in `/etc/hosts` (Mac: `sudo nano /etc/hosts`):

```text
192.168.1.10 monitoring.forge.local db.forge.local
```

`forge.local` selbst braucht keinen Eintrag, das macht Avahi. Die IP ist
DHCP; wandert sie, muss nur diese Zeile nachgezogen werden (oder der Router
gibt dem Pi eine feste Adresse, das ist die bessere Lösung).

## 6. Backup verstehen und testen

### Was ein Backup ist und was nicht

Ein Backup-Lauf (`--profile backup run --rm backup`) erzeugt ein Verzeichnis
`<Zeitstempel>Z/` unter `/srv/forge/data/backups/` und spiegelt es per rsync
nach `BACKUP_SHARE` (`/srv/forge/backup-share`). Darin:

| Datei | Inhalt |
| --- | --- |
| `database.dump` | `pg_dump` im Custom-Format: alle Tabellen und Daten |
| `manifest.txt` | Git-Revision, Zeitpunkt, Datenbankname |
| `SHA256SUMS` | Prüfsummen, werden beim Restore geprüft |

Aufbewahrung regelt das Backup selbst: die letzten 30 Läufe bleiben, dazu
je Monat eine Kopie unter `backups/monthly/<JJJJ-MM>/`, davon die letzten 12.
Der Erfolg jedes Laufs landet als Metrik im Pushgateway (Grafana, Dashboard
„Forge Continuity", Panel „Backup age / result"; Alerts `ForgeBackupStale`,
`ForgeBackupCritical`, `ForgeBackupTransferFailed`).

**Nicht** im Backup: `.env`, die Secrets, das Zertifikat, die
Grafana-/pgAdmin-Datenbanken. Deshalb gehören `~/forge/deploy/.env` und
`/etc/forge/secrets/` gesondert gesichert (Passwort-Manager oder
verschlüsselte Kopie), sonst lässt sich ein Backup zwar einspielen, aber
niemand kann sich anmelden.

### Passwörter und Backups: was zusammenhängt und was nicht

Die Passwörter stecken **nicht** im Dump. Ein Restore spielt Daten in die
laufende Datenbank ein und benutzt dafür das aktuelle Postgres-Passwort aus
`postgres_password.txt`. Ein altes Backup mit inzwischen geänderten
Passwörtern funktioniert also. Im Einzelnen:

- **Postgres-Passwort.** Es lebt an zwei Stellen: in der Secret-Datei und im
  Datenverzeichnis `/srv/forge/data/postgres` (dort wird es beim allerersten
  Start gesetzt). Ändert man nur die Datei, meldet der nächste Deploy
  `password authentication failed`. Das ist der Fehler vom alten Testserver.
  Der Dump hat damit nichts zu tun. Reparatur ohne Datenverlust: der
  `ALTER USER`-Befehl in `deploy/README.md`, Abschnitt „PostgreSQL-Passwort
  stimmt nicht". `/srv/forge/data/postgres` nie löschen, außer die Daten sind
  wegwerfbar.
- **Django Secret Key.** Nicht im Dump. Eine Änderung wirft alle Nutzer aus
  ihren Sitzungen; die Benutzerpasswörter in der Datenbank bleiben gültig,
  weil Django sie mit eigenem Salt hasht.
- **Bexio-Token.** Nicht im Dump; Rotation siehe Abschnitt 4.
- **Grafana, pgAdmin.** Die Secret-Dateien gelten nur beim ersten Start,
  danach liegen die Passwörter in deren eigenen Daten unter `/srv/forge/data/`.
  Ändern in der Oberfläche, nicht über die Datei.
- **Basic-Auth vor pgAdmin.** Kommt bei jedem nginx-Start aus
  `admin_htpasswd.txt`, lässt sich also wie das Token rotieren.

### Restore, zwei Wege

1. **Restore-Verification** (Profil `restore-verification`): spielt ein Backup
   in ein *separates* Postgres ein, lässt Django-Checks und Migrationen
   prüfen und räumt wieder auf. Die Produktionsdatenbank bleibt unberührt.
   Das ist der Test, den man monatlich fahren sollte.
2. **Echter Restore** (`scripts/restore-postgres.sh`): löscht das Schema in der
   Produktionsdatenbank und spielt den Dump ein. Nur bewusst, mit
   `CONFIRM_RESTORE_POSTGRES=true`, Wartungsmodus bleibt danach an, bis man
   ihn nach eigener Prüfung beendet.

### Ablauf auf diesem Pi (2026-09-14)

```bash
cd ~/forge/deploy
./scripts/compose.sh --profile backup run --rm backup                 # ca. 1 Sekunde, 0,5 MB bei 1760 Rechnungen
ls /srv/forge/data/backups /srv/forge/backup-share                     # gleicher Zeitstempel an beiden Orten
```

Ergebnis: `20260914T194109Z/` mit `database.dump` (158 KB), `manifest.txt`
(Revision `6086749`), `SHA256SUMS`; Spiegel auf dem Share, Monatskopie
`monthly/2026-09`, Pushgateway `backup_last_attempt_success 1`.

Restore-Verifikation gegen genau dieses Backup:

```bash
sed -i 's|^RESTORE_BACKUP=.*|RESTORE_BACKUP=/srv/forge/backup-share/20260914T194109Z|' .env
./scripts/compose.sh --profile restore-verification run --rm restore-verify
./scripts/compose.sh --profile restore-verification rm -sf restore-postgres restore-verify   # aufräumen
docker volume rm forge_restore_postgres_data
```

Ergebnis: Prüfsummen OK, Dump in das isolierte Postgres eingespielt,
`manage.py check` ohne Befund, alle 35 Migrationen als angewendet erkannt.
Nie `compose down` mit Profil zum Aufräumen benutzen, das entfernt auch die
Kern-Dienste.

Nächtliches Backup, 02:30 Uhr, als `elias_admin`:

```bash
(crontab -l 2>/dev/null; echo '30 2 * * * cd /home/elias_admin/forge/deploy && ./scripts/compose.sh --profile backup run --rm backup >> /home/elias_admin/forge-backup.log 2>&1') | crontab -
```

Offener Punkt: `BACKUP_SHARE` liegt auf derselben SD-Karte wie die Datenbank.
Stirbt die Karte, sind Original und Kopie weg. Für den Testserver akzeptabel,
für den VPS gehört der Share auf einen zweiten Datenträger oder ein externes
Ziel (NAS, Object Storage).

## 7. Zugänge und Alltag

| Was | Wo | Login |
| --- | --- | --- |
| App | `https://forge.local/` | `admin` + `~/forge-admin-login.txt` auf dem Pi |
| Django-Admin | `https://forge.local/admin/` | dito; dort weitere Benutzer und Gruppen anlegen |
| Grafana | `https://monitoring.forge.local/` | `admin` + `GRAFANA_ADMIN_PASSWORD` |
| pgAdmin | `https://db.forge.local/` | erst Basic-Auth `admin` + `ADMIN_BASIC_AUTH_PASSWORD`, dann `admin@forge-betrieb.de` + `PGADMIN_PASSWORD` |

Das Zertifikat ist selbstsigniert; der Browser warnt einmal pro Name. Für
`monitoring.` und `db.` braucht jeder Client den `/etc/hosts`-Eintrag aus
Abschnitt 5.

```bash
cd ~/forge/deploy
git pull && ./scripts/validate-config.sh && ./scripts/deploy.sh    # Update einspielen
./scripts/compose.sh ps                                            # Zustand aller Container
./scripts/compose.sh logs --tail=200 web celery-worker nginx       # Logs
./scripts/maintenance.sh status                                    # Wartungs-/Lock-Zustand
tail ~/forge-backup.log                                            # letzte nächtliche Backups
```

Bexio-Token erneuern: Abschnitt 4. Backup wiederherstellen: Abschnitt 6 und
`deploy/README.md`, „PostgreSQL-Restore".
