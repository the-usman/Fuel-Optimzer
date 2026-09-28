"""Unit tests for request validation."""

from __future__ import annotations

from apps.routing.api.serializers import MAX_LOCATION_LENGTH, RouteRequestSerializer


def test_trims_whitespace():
    serializer = RouteRequestSerializer(data={"start": "  Chicago, IL ", "finish": "Denver, CO"})

    assert serializer.is_valid()
    assert serializer.validated_data == {"start": "Chicago, IL", "finish": "Denver, CO"}


def test_requires_both_fields():
    serializer = RouteRequestSerializer(data={"start": "Chicago, IL"})

    assert not serializer.is_valid()
    assert set(serializer.errors) == {"finish"}


def test_rejects_blank_and_overlong_values():
    serializer = RouteRequestSerializer(
        data={"start": "   ", "finish": "x" * (MAX_LOCATION_LENGTH + 1)}
    )

    assert not serializer.is_valid()
    assert set(serializer.errors) == {"start", "finish"}
