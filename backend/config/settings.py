"""
Django settings for AgriAura.

Everything that differs between a laptop and a server is read from environment
variables (see .env.example). With no variables set the project runs exactly as
before: SQLite, DEBUG on, a throw-away dev secret key. With DJANGO_DEBUG=False it
refuses to start without a real DJANGO_SECRET_KEY.
"""

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)

_DEV_SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ""
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Generate one with: "
            "python -c \"from django.core.management.utils import get_random_secret_key as g; print(g())\""
        )
    SECRET_KEY = _DEV_SECRET_KEY

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "advisory",
    "validation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves /static/ (admin CSS) from gunicorn
    # CorsMiddleware MUST be before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "advisory.middleware.NoCacheMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def _database_from_url(url: str) -> dict:
    """postgres://user:pass@host:5432/dbname?sslmode=require -> Django DATABASES entry."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(f"DATABASE_URL scheme '{parsed.scheme}' is not supported; use postgres://")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "localhost",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": dict(parse_qsl(parsed.query)),  # e.g. sslmode=require
    }


if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": _database_from_url(os.environ["DATABASE_URL"])}
else:
    # Local development: a single SQLite file.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "timeout": 20,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL;",
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# "Today" for syncs and alerts follows this zone: set DJANGO_TIME_ZONE=Asia/Kolkata on the server.
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Background weather scheduler ────────────────────────────────────────────
# Automatically syncs Open-Meteo history + forecast data for every farm on an
# interval, with no manual intervention required (advisory/scheduler.py,
# started from advisory/apps.py). Every run — scheduled, manual, or CLI — is
# logged to the SchedulerLog model.
SCHEDULER_AUTOSTART = os.environ.get("SCHEDULER_AUTOSTART", "True") == "True"
WEATHER_SYNC_INTERVAL_MINUTES = int(os.environ.get("WEATHER_SYNC_INTERVAL_MINUTES", "60"))
WEATHER_SYNC_MAX_RETRIES = int(os.environ.get("WEATHER_SYNC_MAX_RETRIES", "3"))

# Demo data. When True the dashboard may silently regenerate SYNTHETIC weather for the
# first farm if its newest stored day is before today. Fine for a laptop demo; it must be
# off wherever real readings are stored, so it defaults to on only while DEBUG is on.
DEMO_AUTOSEED = env_bool("DEMO_AUTOSEED", DEBUG)

# ── Production security (only when DEBUG is off) ─────────────────────────────
# TLS is normally terminated by a reverse proxy in front of the container;
# DJANGO_HTTPS=True tells Django requests really arrived over https.
if not DEBUG:
    if env_bool("DJANGO_HTTPS", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}

# ── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# ── CORS ─────────────────────────────────────────────────────────────────────
# In development the Vite proxy forwards /api/* requests to Django as same-origin,
# so CORS headers are NOT required for dev. They are still set here so the app
# works in production without a reverse proxy too.
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
).split(",")

CORS_ALLOW_CREDENTIALS = True

# Whitelist all headers the browser may send — prevents preflight rejection.
CORS_ALLOW_HEADERS = list(default_headers) + [
    "cache-control",
    "pragma",
    "expires",
    "x-requested-with",
]

# Allow all HTTP methods for the API
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
