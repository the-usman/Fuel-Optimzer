"""Input validation for the route endpoint, shared by the GET and POST variants."""

from __future__ import annotations

from rest_framework import serializers

MAX_LOCATION_LENGTH = 200


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=MAX_LOCATION_LENGTH, trim_whitespace=True)
    finish = serializers.CharField(max_length=MAX_LOCATION_LENGTH, trim_whitespace=True)
