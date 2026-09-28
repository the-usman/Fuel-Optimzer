"""Versioned API routes for trip planning and health checks."""

from __future__ import annotations

from django.urls import path

from apps.routing.api.views import HealthView, RouteView

urlpatterns = [
    path("route/", RouteView.as_view(), name="route"),
    path("health/", HealthView.as_view(), name="health"),
]
