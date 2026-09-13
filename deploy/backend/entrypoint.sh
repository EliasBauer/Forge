#!/bin/sh
set -eu

for required in DJANGO_SECRET_KEY_FILE POSTGRES_PASSWORD_FILE MEILISEARCH_MASTER_KEY_FILE; do
  eval "path=\${$required:-}"
  test -n "$path" && test -r "$path" || {
    echo "$required must reference a readable secret file" >&2
    exit 1
  }
done

exec "$@"
