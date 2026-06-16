# ADR 001 – GeneralManager als Backend-Framework

**Datum:** 2026-02-25
**Status:** Akzeptiert

## Kontext

Das Projekt benötigt ein Django-Backend mit GraphQL-API, Caching, Suche und optionalen WebSocket-Subscriptions. Wir haben folgende Optionen verglichen:

- Reines Django + manuelles GraphQL-Setup
- Django REST Framework + REST-API
- **GeneralManager** (Open-Source, Django-basiert)

## Entscheidung

Wir nutzen **GeneralManager** als Dependency (PyPI: `GeneralManager`).

## Begründung

- **Domain-First**: Manager + Interface-Pattern erzwingt klare Trennung von Business Logic und Datenhaltung
- **GraphQL Auto-Generation**: Queries und Mutations werden aus dem Domain-Modell abgeleitet – weniger Boilerplate
- **Caching mit Dependency-Tracking**: automatische Cache-Invalidierung ohne manuelle Cache-Keys
- **Such-Integration**: DevSearchBackend (lokal, kein Service) und MeilisearchBackend (Prod) sind austauschbar konfigurierbar
- **Referenzprojekt**: `outer_rim_logistics` im Upstream-Repo als konkretes Muster

## Konsequenzen

- Wir folgen den GeneralManager-Patterns (siehe `docs/general_manager-patterns.md`)
- Keine parallele REST-API – alles läuft über GraphQL
- Caching nur über GM-Mechanismen, keine freistehenden `cache.set()`-Aufrufe
- Bei Breaking Changes im Upstream muss die Abhängigkeit geprüft werden

## Verworfene Alternativen

- **Reines Django + graphene-django**: mehr Boilerplate, kein Dependency-Tracking
- **DRF + REST**: REST passt weniger zu den verschachtelten Datenstrukturen des Projektcontrollings
