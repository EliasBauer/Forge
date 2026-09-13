FROM node:22-slim AS frontend-base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM frontend-base AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM debian:trixie-slim AS nginx-base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gettext-base \
    nginx \
    openssl \
    && rm -rf /var/lib/apt/lists/*

FROM nginx-base

RUN rm -f /etc/nginx/sites-enabled/default

COPY --from=frontend /frontend/dist /usr/share/nginx/html
COPY deploy/nginx/nginx.conf.template /etc/nginx/templates/forge.conf.template
COPY deploy/nginx/entrypoint.sh /entrypoint.sh
COPY deploy/nginx/maintenance.html /usr/share/nginx/html/
RUN chmod 0555 /entrypoint.sh

EXPOSE 80 443
ENTRYPOINT ["/entrypoint.sh"]
