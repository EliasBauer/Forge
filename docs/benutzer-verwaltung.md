# Benutzerverwaltung – Forge

> Alle Aktionen erfordern Admin-Zugang zum Django Admin (`/admin/`).

## Ersteinrichtung: Gruppen anlegen

Einmalig nach der Installation ausführen:

```bash
uv run python manage.py create_groups
```

Dies legt die vier Gruppen an: **Admin**, **Projektleiter**, **Betrachter**, **Monteur**.

---

## Benutzer anlegen

1. Django Admin öffnen: `http://<server>/admin/`
2. **Authentifizierung und Autorisierung → Benutzer → Benutzer hinzufügen**
3. Benutzername + Passwort eingeben → **Speichern**
4. Im nächsten Schritt unter **Gruppen** die passende Gruppe zuweisen

### Gruppen und ihre Bedeutung

| Gruppe            | Bedeutung                                              |
| ----------------- | ------------------------------------------------------ |
| **Admin**         | Vollzugriff + Benutzerverwaltung                       |
| **Projektleiter** | Projekte anlegen/bearbeiten, Stundensätze verwalten    |
| **Betrachter**    | Lesezugriff auf alles (für Inhaber/GF)                 |
| **Monteur**       | Nur Stunden-Ist bearbeiten; keine Finanzdaten sichtbar |

> Ein Benutzer sollte **genau einer** Gruppe angehören.

---

## Passwort zurücksetzen (als Admin)

### Option 1: Django Admin

1. **Authentifizierung und Autorisierung → Benutzer** → Benutzer anklicken
2. Unten: **Passwort** → **Dieses Passwort-Formular**
3. Neues Passwort eingeben → **Speichern**

### Option 2: Management-Befehl (via Shell)

```bash
uv run python manage.py changepassword <benutzername>
```

Das Passwort wird interaktiv abgefragt (kein Klartext in der Shell-Historie).

---

## Superuser anlegen (für neuen Admin)

```bash
uv run python manage.py createsuperuser
```

Danach im Django Admin die **Admin**-Gruppe zuweisen.

---

## Schnellreferenz

| Aktion                 | Befehl / Weg                                    |
| ---------------------- | ----------------------------------------------- |
| Gruppen initialisieren | `uv run python manage.py create_groups`         |
| Benutzer anlegen       | Django Admin → Benutzer hinzufügen              |
| Passwort zurücksetzen  | Django Admin → Benutzer → Passwort ändern       |
| Passwort per Shell     | `uv run python manage.py changepassword <name>` |
| Superuser anlegen      | `uv run python manage.py createsuperuser`       |
