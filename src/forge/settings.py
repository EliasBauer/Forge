import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent

FORGE_ENV = os.environ.get("FORGE_ENV", "production")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-in-production",
)

# if os.getenv("FORGE_ENV") == "dev":
# from dotenv import load_dotenv

# load_dotenv()

BEXIO_ACCESS_TOKEN = os.environ.get("BEXIO_ACCESS_TOKEN")
# Im Dev-Modus werden Fixture-Daten statt echter Bexio-API genutzt
BEXIO_DEV_MODE = not bool(BEXIO_ACCESS_TOKEN)

DEBUG = FORGE_ENV == "dev"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "daphne",
    "channels",
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
    "forge.middleware.DisableCSRFForGraphQL",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
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
if FORGE_ENV == "dev":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    import dj_database_url

    _database_url = os.environ.get(
        "DATABASE_URL", "postgres://forge:forge@db:5432/forge"
    )
    DATABASES = {
        "default": dj_database_url.parse(_database_url, conn_max_age=600),  # type: ignore
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
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Celery ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Jeden Mittwoch um 02:00 Uhr (Europe/Zurich)
    "bexio-sync-weekly": {
        "task": "bexio.sync_lieferantenrechnungen",
        "schedule": crontab(hour=2, minute=0, day_of_week=3),
    },
}

GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "DEFAULT_PERMISSIONS": {
        "READ": ["public"],
        "CREATE": ["isAuthenticated"],
        "UPDATE": ["isAuthenticated"],
        "DELETE": ["isAuthenticated"],
    },
}
