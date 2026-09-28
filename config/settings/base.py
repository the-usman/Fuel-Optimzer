"""Base settings shared by every environment, read from environment variables."""

from __future__ import annotations

from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.stations",
    "apps.routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": config("SQLITE_PATH", default=str(BASE_DIR / "db.sqlite3")),
    }
}

REDIS_URL = config("REDIS_URL", default="")
ROUTE_CACHE_TTL_SECONDS = config("ROUTE_CACHE_TTL_SECONDS", default=86400, cast=int)

CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
        if REDIS_URL
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "routes"}
    )
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "apps.routing.api.exception_handler.api_exception_handler",
}

OSRM_BASE_URL = config("OSRM_BASE_URL", default="https://router.project-osrm.org")
OSRM_PROFILE = config("OSRM_PROFILE", default="driving")
OSRM_TIMEOUT_SECONDS = config("OSRM_TIMEOUT_SECONDS", default=10.0, cast=float)
NOMINATIM_URL = config("NOMINATIM_URL", default="https://nominatim.openstreetmap.org/search")
NOMINATIM_TIMEOUT_SECONDS = config("NOMINATIM_TIMEOUT_SECONDS", default=5.0, cast=float)
NOMINATIM_MIN_INTERVAL_SECONDS = config("NOMINATIM_MIN_INTERVAL_SECONDS", default=1.0, cast=float)
HTTP_USER_AGENT = config("HTTP_USER_AGENT", default="fuel-route-optimizer/1.0 (assessment project)")
HTTP_CONNECT_RETRIES = config("HTTP_CONNECT_RETRIES", default=2, cast=int)

VEHICLE_RANGE_MILES = config("VEHICLE_RANGE_MILES", default=500.0, cast=float)
VEHICLE_MPG = config("VEHICLE_MPG", default=10.0, cast=float)
STARTING_FUEL_GALLONS = config("STARTING_FUEL_GALLONS", default=0.0, cast=float)
CORRIDOR_MILES = config("CORRIDOR_MILES", default=10.0, cast=float)
ORIGIN_SEARCH_MILES = config("ORIGIN_SEARCH_MILES", default=40.0, cast=float)
SIMPLIFY_TOLERANCE_DEGREES = config("SIMPLIFY_TOLERANCE_DEGREES", default=0.005, cast=float)
COORDINATE_CACHE_PRECISION = config("COORDINATE_CACHE_PRECISION", default=4, cast=int)

CONTIGUOUS_US_BOUNDS = {
    "min_lat": 24.39,
    "max_lat": 49.39,
    "min_lng": -124.85,
    "max_lng": -66.88,
}

GAZETTEER_PATH = DATA_DIR / "us_places_gazetteer.txt"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"apps": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")}},
}
