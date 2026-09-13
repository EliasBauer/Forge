"""Erkennt die exakte synthetische GraphQL-Probe (Blackbox/deploy.sh)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from django.http import HttpRequest

_GRAPHQL_PATHS: Final = frozenset({"/graphql", "/graphql/"})
_HEALTH_OPERATION_NAME: Final = "HealthProbe"
_HEALTH_QUERY: Final = re.compile(
    r"[ \t\r\n]*query[ \t\r\n]+HealthProbe[ \t\r\n]*"
    r"\{[ \t\r\n]*__typename[ \t\r\n]*\}[ \t\r\n]*"
)


def _query_parameter(request: HttpRequest, name: str) -> str | None:
    query_parameters = getattr(request, "GET", None)
    get = getattr(query_parameters, "get", None)
    if not callable(get):
        return None
    value = get(name)
    return value if isinstance(value, str) else None


def is_synthetic_graphql_health_probe(
    request: HttpRequest,
    *,
    query: str | None = None,
    operation_name: str | None = None,
) -> bool:
    """Return whether a request is the exact public synthetic GraphQL probe."""
    if getattr(request, "method", None) != "GET":
        return False
    if getattr(request, "path_info", None) not in _GRAPHQL_PATHS:
        return False

    resolved_query = query if query is not None else _query_parameter(request, "query")
    resolved_operation_name = (
        operation_name
        if operation_name is not None
        else _query_parameter(request, "operationName")
    )
    return (
        resolved_operation_name == _HEALTH_OPERATION_NAME
        and isinstance(resolved_query, str)
        and _HEALTH_QUERY.fullmatch(resolved_query) is not None
    )
