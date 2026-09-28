"""The one place where exceptions become HTTP responses.

Every error, whether a DRF validation error or a domain exception, is rendered in the same
shape: ``{"error": {"code": ..., "message": ..., "details": ...}}``.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.routing.domain import exceptions as domain

DOMAIN_STATUS: tuple[tuple[type[domain.TripPlanningError], int], ...] = (
    (domain.InvalidLocationError, status.HTTP_400_BAD_REQUEST),
    (domain.LocationNotFoundError, status.HTTP_400_BAD_REQUEST),
    (domain.OutsideServiceAreaError, status.HTTP_400_BAD_REQUEST),
    (domain.NoRouteFoundError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (domain.NoFeasibleRouteError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (domain.NoStationNearOriginError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (domain.RoutingTimeoutError, status.HTTP_504_GATEWAY_TIMEOUT),
    (domain.RoutingProviderError, status.HTTP_502_BAD_GATEWAY),
)


def error_response(
    code: str, message: str, status_code: int, details: dict[str, Any] | None = None
) -> Response:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return Response({"error": body}, status=status_code)


def domain_status(exc: domain.TripPlanningError) -> int:
    for exception_type, status_code in DOMAIN_STATUS:
        if isinstance(exc, exception_type):
            return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def domain_details(exc: domain.TripPlanningError) -> dict[str, Any] | None:
    if isinstance(exc, domain.NoFeasibleRouteError):
        return {"gap_start_mile": exc.gap_start_mile, "gap_end_mile": exc.gap_end_mile}
    return None


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, domain.TripPlanningError):
        return error_response(exc.code, exc.message, domain_status(exc), domain_details(exc))
    if isinstance(exc, ValidationError):
        return error_response(
            "invalid_request", "The request parameters are invalid.", exc.status_code, exc.detail
        )
    if isinstance(exc, Http404):
        return error_response("not_found", "Resource not found.", status.HTTP_404_NOT_FOUND)
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, APIException):
        return error_response(exc.default_code, str(exc.detail), response.status_code)
    return response
