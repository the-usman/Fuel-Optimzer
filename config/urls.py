"""Root URL configuration wiring the versioned API and the HTML map page."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from apps.routing.web.views import route_map_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.routing.urls")),
    path("map/<str:route_id>/", route_map_view, name="route-map"),
]
