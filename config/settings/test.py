"""Test settings: in-memory database and cache, no real network endpoints."""

from __future__ import annotations

from .base import *

DEBUG = False
SECRET_KEY = "test-secret-key"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
OSRM_BASE_URL = "https://osrm.test"
NOMINATIM_URL = "https://nominatim.test/search"
NOMINATIM_MIN_INTERVAL_SECONDS = 0.0
HTTP_CONNECT_RETRIES = 0
ALLOWED_HOSTS = ["testserver", "localhost"]
LOGGING = {"version": 1, "disable_existing_loggers": False}
