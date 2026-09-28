"""Read friendly admin listing for imported fuel stations."""

from __future__ import annotations

from django.contrib import admin

from apps.stations.models import Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("opis_id", "name", "city", "state", "retail_price")
    list_filter = ("state",)
    search_fields = ("name", "city", "opis_id")
