"""HTTP-Metriken je API (GraphQL, Auth-REST) mit begrenzter Label-Kardinalitaet."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, Literal

from prometheus_client import Counter, Histogram

from forge.observability.graphql_probe import is_synthetic_graphql_health_probe

if TYPE_CHECKING:
    from django.http import HttpRequest

ApiName = Literal["graphql", "auth"]
ApiClassification = tuple[ApiName, str]

_GRAPHQL_PATHS: Final = frozenset({"/graphql", "/graphql/"})
_AUTH_PREFIX: Final = "/api/"
_AUTH_ROUTE_PREFIX: Final = "api/"
_SAFE_ROUTE_FAMILY: Final = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_LATENCY_BUCKETS: Final = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_STANDARD_METHODS: Final = frozenset(
    {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
)

API_REQUESTS = Counter(
    "forge_api_requests_total",
    "Forge API requests split by protocol and bounded endpoint group.",
    ("api", "endpoint_group", "method", "status"),
)
API_REQUEST_DURATION = Histogram(
    "forge_api_request_duration_seconds",
    "Forge API time to response headers in seconds.",
    ("api", "endpoint_group", "method"),
    buckets=_LATENCY_BUCKETS,
)


def _auth_endpoint_group(request: HttpRequest) -> str:
    # Nur aufgeloeste Routen liefern eine Gruppe; freie Pfade bleiben "unmatched",
    # damit Angreifer keine neuen Label-Werte erzeugen koennen.
    resolver_match = getattr(request, "resolver_match", None)
    route = getattr(resolver_match, "route", "") if resolver_match else ""
    if not route.startswith(_AUTH_ROUTE_PREFIX):
        return "unmatched"
    family = route.removeprefix(_AUTH_ROUTE_PREFIX).split("/", 1)[0]
    return family if _SAFE_ROUTE_FAMILY.fullmatch(family) else "other"


def classify_api_request(request: HttpRequest) -> ApiClassification | None:
    if request.path_info in _GRAPHQL_PATHS:
        if is_synthetic_graphql_health_probe(request):
            return None
        return "graphql", "graphql"
    if request.path_info.startswith(_AUTH_PREFIX):
        return "auth", _auth_endpoint_group(request)
    return None


def _normalize_method(method: str) -> str:
    normalized_method = method.upper() if method else "OTHER"
    return normalized_method if normalized_method in _STANDARD_METHODS else "OTHER"


def record_api_response(
    classification: ApiClassification,
    *,
    method: str,
    status: int,
    duration_seconds: float,
) -> None:
    api, endpoint_group = classification
    normalized_method = _normalize_method(method)
    normalized_status = str(status)
    API_REQUESTS.labels(
        api=api,
        endpoint_group=endpoint_group,
        method=normalized_method,
        status=normalized_status,
    ).inc()
    API_REQUEST_DURATION.labels(
        api=api,
        endpoint_group=endpoint_group,
        method=normalized_method,
    ).observe(max(duration_seconds, 0.0))
