"""Django application configuration for the stations app."""

from __future__ import annotations

from django.apps import AppConfig


class StationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.stations"
    label = "stations"
