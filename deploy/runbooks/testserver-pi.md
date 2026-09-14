# Runbook: Testserver Raspberry Pi neu aufsetzen

Ziel: `telias@testserver.local` (Raspberry Pi 5) von der leeren SD-Karte bis
zum laufenden Forge-Stack von `main`, mit getestetem Backup. Jeder Befehl mit
dem Grund dahinter. Die allgemeine Kurzanleitung ist
[`docs/start_prod.md`](../../docs/start_prod.md); hier steht nur, was auf dem
Pi konkret passiert. Stand: 2026-09-14, Neuaufsetzen Nr. 2.

## 1. SD-Karte flashen (am Mac, Raspberry Pi Imager)

- Gerät: Raspberry Pi 5. Betriebssystem: **Raspberry Pi OS Lite (64-bit)**,
  Debian 13 „trixie". Lite, weil kein Desktop gebraucht wird und der Pi den
  RAM für den Stack braucht (rund 2 GB).
- Anpassungen im Imager (Zahnrad / „Einstellungen bearbeiten"):
  - Hostname `testserver` → mDNS-Name `testserver.local`.
  - Benutzer `telias`, Passwort setzen (nur für `sudo`, nicht für SSH).
  - SSH aktivieren, **nur Public-Key-Authentifizierung**, den öffentlichen
    Schlüssel vom Mac eintragen (`cat ~/.ssh/id_ed25519.pub`).
  - WLAN nicht konfigurieren, der Pi hängt per Kabel am Router.
  - Zeitzone `Europe/Zurich`, Tastatur egal (kein Bildschirm).
- Karte in den Pi, Strom dran, etwa zwei Minuten warten.

## 2. Erster Login und Grundpakete

```bash
ssh-keygen -R testserver.local      # alten Host-Key vom vorigen Pi vergessen, sonst warnt SSH
ssh telias@testserver.local
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
sudo OPERATOR=telias APP_DOMAIN=testserver.local sh ~/forge/deploy/scripts/host-prep.sh
```

Was es tut, und warum:

- Gruppe `forge-deploy` und `telias` hinein: nur diese Gruppe darf `.env`,
  Secrets und den TLS-Schlüssel lesen. Dazu `telias` in `docker`.
- `/srv/forge/data/...` mit den festen Container-UIDs (Backend 1000,
  Prometheus 65534, Grafana 472, Loki 10001, pgAdmin 5050). Der Preflight
  prüft genau diese Eigentümer und repariert nichts.
- `/etc/forge/secrets` (0750, Gruppe `forge-deploy`): Secrets liegen
  außerhalb des Checkouts, `SECRETS_DIR` in `.env` zeigt dorthin.
- Selbstsigniertes Zertifikat für `testserver.local`,
  `monitoring.testserver.local`, `db.testserver.local`. Bewusst **ohne IP**
  im SAN: die IP kommt per DHCP und darf sich ändern, die Namen nicht.
- SSH: Passwort-Login und Root-Login aus (nur wenn ein Schlüssel hinterlegt ist).
- `unattended-upgrades`: Debian-Sicherheitsupdates laufen nachts automatisch.

Danach **ausloggen und neu einloggen**, sonst gelten die Gruppen nicht.

Nur auf dem Pi zusätzlich, weil `testserver.local` über mDNS aufgelöst wird:

```bash
sudo sed -i 's/^use-ipv6=yes/use-ipv6=no/' /etc/avahi/avahi-daemon.conf && sudo systemctl restart avahi-daemon
```

Avahi nennt sonst auch die IPv6-Adresse vom Provider; Browser probieren die
zuerst und hängen, wenn sie sich ändert oder gefiltert wird.

## 4. Konfiguration und Secrets

_(wird beim Aufsetzen ergänzt)_

## 5. Deploy

_(wird beim Aufsetzen ergänzt)_

## 6. Backup testen

_(wird beim Aufsetzen ergänzt)_
