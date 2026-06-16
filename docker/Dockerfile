# ---- Builder ----
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/

# ---- Runtime ----
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# TODO: adjust once Django is set up (add collectstatic, migrate, etc.)
CMD ["gunicorn", "jane.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
