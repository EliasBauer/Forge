# ADR 002 – Bexio-Sync via Celery Beat

**Datum:** 2026-02-25
**Status:** Akzeptiert

## Kontext

Bexio-Daten (Rechnungen, Projekte, Kosten) müssen mindestens täglich synchronisiert werden. Optionen:

- Host-Cronjob (crontab auf Raspberry Pi)
- Separater Cron-Container in Docker Compose
- **Celery Beat** (periodische Tasks im bestehenden Stack)

## Entscheidung

Bexio-Sync wird via **Celery Beat + Celery Worker** umgesetzt.

## Begründung

- Redis und Celery sind ohnehin im Stack (GeneralManager nutzt Celery für async Search-Indexing)
- Retry-Logik bei API-Fehlern ist in Celery nativ vorhanden
- Monitoring über Celery-Flower möglich (optional, Phase 2)
- Kein zusätzlicher Container oder Host-Abhängigkeit nötig

## Konsequenzen

- `celery-worker` und `celery-beat` Container sind Pflicht im Docker Compose
- Bexio API-Credentials kommen aus ENV-Variablen (kein Hardcoding)
- Auth-Methode mit Bexio (API Key oder OAuth) muss vor Implementierung geklärt werden

## Verworfene Alternativen

- **Host-Cronjob**: Kopplung an Betriebssystem, keine Retry-Logik, schwerer zu überwachen
- **Cron-Container**: Zusätzlicher Container ohne Mehrwert gegenüber Celery Beat
