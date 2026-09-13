FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    DJANGO_SETTINGS_MODULE=forge.settings \
    PYTHONPATH=/app/src \
    PATH=/app/.venv/bin:$PATH

# postgresql-client 17 (trixie) passt zu postgres:17 fuer pg_dump/pg_restore.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        coreutils \
        curl \
        postgresql-client \
        rsync \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.13

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY manage.py ./
COPY src ./src
COPY deploy/backend/entrypoint.sh /app/deploy/backend/entrypoint.sh
COPY deploy/backup/backup.sh deploy/backup/restore-verify.sh /app/deploy/backup/
RUN chmod 0555 /app/deploy/backend/entrypoint.sh /app/deploy/backup/*.sh \
    && mkdir -p /run/forge /static \
    && chown -R appuser:appuser /run/forge /static

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/deploy/backend/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "forge.asgi:application"]
