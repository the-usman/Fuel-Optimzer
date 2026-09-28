"""Domain exceptions raised by the services and mapped to HTTP responses in one place.

Each exception carries a stable machine readable ``code`` so clients can branch on it.
"""

from __future__ import annotations


class TripPlanningError(Exception):
    code = "trip_planning_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidLocationError(TripPlanningError):
    code = "invalid_location"


class LocationNotFoundError(TripPlanningError):
    code = "location_not_found"


class OutsideServiceAreaError(TripPlanningError):
    code = "outside_service_area"


class NoRouteFoundError(TripPlanningError):
    code = "no_route_found"


class NoFeasibleRouteError(TripPlanningError):
    code = "no_feasible_fuel_plan"

    def __init__(self, message: str, gap_start_mile: float, gap_end_mile: float) -> None:
        super().__init__(message)
        self.gap_start_mile = gap_start_mile
        self.gap_end_mile = gap_end_mile


class NoStationNearOriginError(TripPlanningError):
    code = "no_station_near_origin"


class RoutingProviderError(TripPlanningError):
    code = "routing_provider_error"


class RoutingTimeoutError(TripPlanningError):
    code = "routing_provider_timeout"


class GeocodingProviderError(RoutingProviderError):
    code = "geocoding_provider_error"


class GeocodingTimeoutError(RoutingTimeoutError):
    code = "geocoding_provider_timeout"
