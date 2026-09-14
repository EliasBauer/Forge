import os
from pathlib import Path
from typing import Any

from forge.env import env_bool, env_csv, env_int, env_secret
from forge.graphql_metric_operations import GRAPHQL_METRIC_OPERATION_ALLOWLIST

BASE_DIR = Path(__file__).resolve().parent.parent

FORGE_ENV = os.environ.get("FORGE_ENV", "production")
IS_DEV = FORGE_ENV == "dev"

# Produktion verlangt DJANGO_SECRET_KEY (oder DJANGO_SECRET_KEY_FILE als Docker-Secret).
SECRET_KEY = env_secret(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-in-production" if IS_DEV else None,
    required=not IS_DEV,
)

BEXIO_ACCESS_TOKEN = env_secret("BEXIO_ACCESS_TOKEN") or None
# Im Dev-Modus werden Fixture-Daten statt echter Bexio-API genutzt
BEXIO_DEV_MODE = not bool(BEXIO_ACCESS_TOKEN)

DEBUG = IS_DEV

ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
# Host-Name, unter dem Prometheus /metrics scrapt (forge.observability.metrics_host)
INTERNAL_METRICS_HOST = os.environ.get("INTERNAL_METRICS_HOST", "")
MAINTENANCE_FLAG_FILE = os.environ.get(
    "MAINTENANCE_FLAG_FILE", "/run/forge/maintenance"
)
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "")
LOG_TO_STDOUT = env_bool("LOG_TO_STDOUT", not IS_DEV)

INSTALLED_APPS = [
    "daphne",
    "channels",
    "django_prometheus",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.stunden",
    "apps.projekt",
    "apps.authentication",
    "apps.bexio",
    "graphene_django",
    "general_manager",
]

MIDDLEWARE = [
    "forge.observability.metrics_host.InternalMetricsHostMiddleware",
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "forge.observability.middleware.ApiMetricsMiddleware",
    "forge.middleware.DisableCSRFForGraphQL",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "forge.urls"
WSGI_APPLICATION = "forge.wsgi.application"
ASGI_APPLICATION = "forge.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---
if IS_DEV:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django_prometheus.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "forge"),
            "USER": os.environ.get("POSTGRES_USER", "forge"),
            "PASSWORD": env_secret("POSTGRES_PASSWORD", required=True),
            "HOST": os.environ.get("POSTGRES_HOST", "pgbouncer"),
            "PORT": env_int("POSTGRES_PORT", 5432),
            # 0 = pro Request neue Verbindung (empfohlen hinter pgBouncer)
            "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 0),
            "CONN_HEALTH_CHECKS": True,
            # Pflicht für pgBouncer Transaction-Pooling
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": {"connect_timeout": env_int("POSTGRES_CONNECT_TIMEOUT", 5)},
        }
    }

# --- Cache & Channels ---
REDIS_URL = os.environ.get("REDIS_URL", "")
CHANNEL_LAYERS: dict[str, Any]

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# --- Internationalization ---
LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Zurich"
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Celery ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = env_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1)
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 1800)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 1680)
# Pflicht für den Celery-Exporter (Task-Events)
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    # Jede Nacht um 02:00 Uhr (Europe/Zurich)
    "bexio-sync-nightly": {
        "task": "bexio.sync_lieferantenrechnungen",
        "schedule": crontab(hour=2, minute=0),
    },
}
if not IS_DEV:
    CELERY_BEAT_SCHEDULE["publish-observability-queue-metrics"] = {
        "task": "forge.observability.tasks.publish_observability_queue_metrics",
        "schedule": 60.0,
    }

# --- Suche ---
# Kein MEILISEARCH_URL gesetzt (z. B. im Devcontainer) => GM faellt automatisch auf
# den in-memory DevSearchBackend zurueck (general_manager/search/backend_registry.py).
MEILISEARCH_URL = os.environ.get("MEILISEARCH_URL", "")

GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "DEFAULT_PERMISSIONS": {
        "READ": ["isAdmin"],
        "CREATE": ["isAdmin"],
        "UPDATE": ["isAdmin"],
        "DELETE": ["isAdmin"],
    },
    "GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER": (
        "apps.authentication.graphql_capabilities.CurrentUserCapabilities"
    ),
    "SEARCH_AUTO_REINDEX": True,
    "SEARCH_RECONCILE_ENABLED": True,
    "SEARCH_RECONCILE_INTERVAL_SECONDS": 30,
    "SEARCH_BACKEND": (
        {
            "class": "general_manager.search.backends.meilisearch.MeilisearchBackend",
            "options": {
                "url": MEILISEARCH_URL,
                "api_key": env_secret("MEILISEARCH_MASTER_KEY") or None,
            },
        }
        if MEILISEARCH_URL
        else None
    ),
    # GraphQL-Metriken (Prometheus) nur in Produktion; Operationen ausserhalb der
    # Allowlist werden als "unknown" gezaehlt (begrenzte Label-Kardinalitaet).
    "GRAPHQL_METRICS_ENABLED": not IS_DEV,
    "GRAPHQL_METRICS_BACKEND": "prometheus",
    "GRAPHQL_METRICS_OPERATION_ALLOWLIST": list(GRAPHQL_METRIC_OPERATION_ALLOWLIST),
    "GRAPHQL_METRICS_UNKNOWN_OPERATION_POLICY": "unknown",
    "GRAPHQL_METRICS_RESOLVER_TIMING": False,
}

# --- Produktion hinter nginx (TLS-Terminierung) ---
if not IS_DEV:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^health/", r"^metrics/?$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # 0 = kein HSTS (selbstsignierte Zertifikate brauchen den Browser-Click-through);
    # mit vertrauenswuerdigem Zertifikat DJANGO_SECURE_HSTS_SECONDS=31536000 setzen.
    SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = False

# --- Logging: JSON auf stdout (Container), sonst Django-Default ---
if LOG_TO_STDOUT:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "json"},
        },
        "root": {
            "handlers": ["console"],
            "level": os.environ.get("LOG_LEVEL", "INFO"),
        },
    }
