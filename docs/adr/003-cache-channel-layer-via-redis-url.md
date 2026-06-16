# ADR 003 – Cache/Channel-Layer-Auswahl via REDIS_URL

**Datum:** 2026-02-25
**Status:** Akzeptiert

## Kontext

Django Cache und Django Channels Channel Layer müssen konfiguriert werden. Zwei Optionen:

- Via `DEBUG`-Flag wechseln (Dev = In-Memory, Prod = Redis)
- Via `REDIS_URL` ENV-Variable wechseln

## Entscheidung

Cache und Channel Layer werden via **`REDIS_URL`** umgeschaltet:

- `REDIS_URL` gesetzt → `RedisCache` + `RedisChannelLayer`
- `REDIS_URL` nicht gesetzt → `LocMemCache` + `InMemoryChannelLayer`

## Begründung

- Im DevContainer läuft Redis – wir wollen Prod-Nähe bereits in der Entwicklung
- `DEBUG` beschreibt Logging-/Error-Verhalten, nicht Infrastruktur-Topologie
- ENV-Variable ist expliziter und leichter zu überschreiben (z.B. in CI ohne Redis)

## Konsequenzen

- Lokales Dev ohne Redis ist weiterhin möglich (LocMemCache-Fallback)
- CI-Umgebung ohne Redis kann `REDIS_URL` einfach weglassen
- Spätere Option: DevContainer ohne eingebettete Services → Services separat via `docker-compose.override.yml`
