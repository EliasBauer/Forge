from __future__ import annotations

from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DEPLOY.parent


def test_backend_image_runs_as_non_root_with_uv_lockfile() -> None:
    text = (DEPLOY / "backend/Dockerfile").read_text()
    assert text.startswith("FROM python:3.12-slim-trixie\n")
    assert "USER appuser" in text
    assert "uv sync --frozen --no-dev" in text
    assert "COPY pyproject.toml uv.lock ./" in text
    assert "PYTHONPATH=/app/src" in text
    assert "DJANGO_SETTINGS_MODULE=forge.settings" in text
    assert 'ENTRYPOINT ["/app/deploy/backend/entrypoint.sh"]' in text
    assert (
        'CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "forge.asgi:application"]'
        in text
    )
    assert "--mount=type=" not in text
    assert "COPY deploy /app/deploy" not in text


def test_backend_image_has_backup_tools() -> None:
    text = (DEPLOY / "backend/Dockerfile").read_text()
    for package in (
        "postgresql-client",
        "rsync",
        "coreutils",
        "curl",
        "ca-certificates",
    ):
        assert package in text
    assert "pgdg" not in text
    assert "deploy/backup/backup.sh" in text
    assert "deploy/backup/restore-verify.sh" in text


def test_backend_entrypoint_requires_readable_secret_files() -> None:
    text = (DEPLOY / "backend/entrypoint.sh").read_text()
    assert (
        "DJANGO_SECRET_KEY_FILE POSTGRES_PASSWORD_FILE MEILISEARCH_MASTER_KEY_FILE"
        in text
    )
    assert text.rstrip().endswith('exec "$@"')


def test_nginx_image_builds_frontend_and_installs_runtime_tools_from_debian() -> None:
    text = (DEPLOY / "nginx/Dockerfile").read_text()
    assert "FROM node:22-slim AS frontend-base" in text
    assert "npm ci" in text
    assert "npm run build" in text
    assert "FROM debian:trixie-slim AS nginx-base" in text
    for package in ("nginx", "curl", "openssl", "gettext-base"):
        assert package in text
    assert "COPY --from=frontend /frontend/dist /usr/share/nginx/html" in text
    assert "rm -f /etc/nginx/sites-enabled/default" in text
    assert "EXPOSE 80 443" in text
    assert "--mount=type=secret" not in text
    assert "NODE_AUTH_TOKEN" not in text


def test_compose_uses_postgres_17_matching_the_trixie_client() -> None:
    text = (DEPLOY / "compose.yml").read_text()
    assert "postgres:17-alpine" in text
    assert "postgres:16-alpine" not in text


def test_repository_build_context_excludes_secrets_and_local_artifacts() -> None:
    text = (REPOSITORY_ROOT / ".dockerignore").read_text()
    for entry in (
        "deploy/secrets/*.txt",
        "deploy/.env",
        "**/.env",
        ".git",
        "**/node_modules",
        ".venv",
        "frontend/dist",
    ):
        assert entry in text


def test_git_ignores_real_env_and_secret_files() -> None:
    text = (REPOSITORY_ROOT / ".gitignore").read_text()
    for entry in ("deploy/.env", "deploy/secrets/*.txt"):
        assert entry in text


def test_secret_examples_are_placeholders_or_intentionally_empty() -> None:
    examples = {
        path.name: path.read_text()
        for path in (DEPLOY / "secrets").glob("*.txt.example")
    }
    assert set(examples) == {
        "django_secret_key.txt.example",
        "postgres_password.txt.example",
        "meilisearch_api_key.txt.example",
        "bexio_access_token.txt.example",
        "admin_htpasswd.txt.example",
        "grafana_admin_password.txt.example",
        "pgadmin_password.txt.example",
        "teams_workflow_url.txt.example",
        "smtp_password.txt.example",
    }
    empty_allowed = {
        "bexio_access_token.txt.example",
        "teams_workflow_url.txt.example",
        "smtp_password.txt.example",
    }
    for name, content in examples.items():
        if name in empty_allowed:
            assert content == "", name
        else:
            assert content == "CHANGE_ME\n", name
    assert not list((DEPLOY / "secrets").glob("*.txt"))


def test_entrypoints_are_executable_posix_scripts() -> None:
    for script in (
        "backend/entrypoint.sh",
        "nginx/entrypoint.sh",
        "pgbouncer/entrypoint.sh",
        "pgbouncer-exporter/entrypoint.sh",
    ):
        path = DEPLOY / script
        assert path.read_text().startswith("#!/bin/sh\n"), script
        assert path.stat().st_mode & 0o111, script
