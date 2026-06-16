#!/usr/bin/env bash
# Setzt die lokale Dev-Datenbank zurück und füllt sie mit Basisdaten.
# Spec: specs/setup_db.md
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export FORGE_ENV=dev

# Bevorzugt das Projekt-Venv, fällt auf `uv run python` zurück.
if [[ -x ".venv/bin/python" ]]; then
    PY=(".venv/bin/python")
elif command -v uv >/dev/null 2>&1; then
    PY=("uv" "run" "python")
else
    echo "Fehler: weder .venv/bin/python noch uv gefunden." >&2
    exit 1
fi

DB_FILE="src/db.sqlite3"
APPS=(authentication bexio projekt stunden)

echo "==> Lösche alte Datenbank"
rm -f "$DB_FILE"

echo "==> Lösche alte Migrationen"
for app in "${APPS[@]}"; do
    mig_dir="src/apps/${app}/migrations"
    if [[ -d "$mig_dir" ]]; then
        find "$mig_dir" -maxdepth 1 -type f -name '*.py' ! -name '__init__.py' -delete
        rm -rf "$mig_dir/__pycache__"
    fi
done

echo "==> Erstelle Migrationen"
"${PY[@]}" manage.py makemigrations

echo "==> Wende Migrationen an"
"${PY[@]}" manage.py migrate

echo "==> Bootstrap Dev-Daten (Gruppen, User, Bexio-Sync)"
"${PY[@]}" manage.py setup_dev_data

echo "==> Fertig."
