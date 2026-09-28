"""Thin HTTP views: validate input, delegate to the trip planner, return its payload."""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.routing.api.serializers import RouteRequestSerializer
from apps.routing.services.container import get_trip_planner
from apps.stations.models import Station
from apps.stations.repository import StationRepository


class RouteView(APIView):
    def get(self, request: Request) -> Response:
        return self._plan(request, request.query_params)

    def post(self, request: Request) -> Response:
        return self._plan(request, request.data)

    @staticmethod
    def _plan(request: Request, data: Any) -> Response:
        serializer = RouteRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        payload = get_trip_planner().plan(validated["start"], validated["finish"])
        map_path = reverse("route-map", kwargs={"route_id": payload["route_id"]})
        payload["map"] = {"html_url": request.build_absolute_uri(map_path), **payload["map"]}
        return Response(payload)


class HealthView(APIView):
    def get(self, request: Request) -> Response:
        repository = StationRepository.instance()
        indexed = len(repository.get_index()) if repository.is_loaded else 0
        return Response(
            {
                "status": "ok",
                "station_count": Station.objects.count(),
                "index_loaded": repository.is_loaded,
                "indexed_station_count": indexed,
            }
        )
