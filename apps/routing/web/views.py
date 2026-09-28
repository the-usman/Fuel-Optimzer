"""HTML map page rendered purely from the cached trip; it never calls the routing API."""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.routing.services.container import get_trip_planner


def route_map_view(request: HttpRequest, route_id: str) -> HttpResponse:
    trip = get_trip_planner().cached_trip(route_id)
    if trip is None:
        raise Http404("Unknown or expired route id.")
    return render(request, "routing/map.html", {"trip": trip})
