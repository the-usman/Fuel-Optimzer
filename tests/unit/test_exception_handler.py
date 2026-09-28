"""Unit tests for the single exception handler that shapes every API error."""

from __future__ import annotations

from rest_framework.exceptions import MethodNotAllowed

from apps.routing.api.exception_handler import api_exception_handler
from apps.routing.domain.exceptions import TripPlanningError


def test_unmapped_domain_error_becomes_500():
    response = api_exception_handler(TripPlanningError("boom"), {})

    assert response.status_code == 500
    assert response.data == {"error": {"code": "trip_planning_error", "message": "boom"}}


def test_other_api_exceptions_keep_status_and_use_standard_shape():
    response = api_exception_handler(MethodNotAllowed("PUT"), {"view": None})

    assert response.status_code == 405
    assert response.data["error"]["code"] == "method_not_allowed"


def test_unknown_exceptions_are_left_to_django():
    assert api_exception_handler(RuntimeError("bug"), {}) is None


def test_put_on_route_endpoint_returns_standard_405(client):
    response = client.put("/api/v1/route/")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
