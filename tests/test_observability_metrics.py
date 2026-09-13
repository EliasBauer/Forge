from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import pytest
from asgiref.sync import iscoroutinefunction
from django.http import HttpRequest, HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import Client, RequestFactory, override_settings
from prometheus_client import REGISTRY

from forge.graphql_metric_operations import GRAPHQL_METRIC_OPERATION_ALLOWLIST
from forge.observability.api_metrics import (
    API_REQUEST_DURATION,
    classify_api_request,
    record_api_response,
)
from forge.observability.metrics_host import _is_ip_host
from forge.observability.middleware import ApiMetricsMiddleware, SyncGetResponse

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SOURCE = REPOSITORY_ROOT / "frontend/src"
DOCUMENT_PATTERN = re.compile(r"\bgql\s*`(?P<document>.*?)`", re.DOTALL)
OPERATION_PATTERN = re.compile(
    r"^[ \t]*(?:query|mutation|subscription)[ \t]+([_A-Za-z][_0-9A-Za-z]*)",
    re.MULTILINE,
)

METRICS_HOST_SETTINGS = {
    "ALLOWED_HOSTS": ["testserver", "web"],
    "INTERNAL_METRICS_HOST": "web",
}


def _strip_typescript_comments(contents: str) -> str:
    stripped: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(contents):
        character = contents[index]
        if quote is not None:
            stripped.append(character)
            if character == "\\" and index + 1 < len(contents):
                index += 1
                stripped.append(contents[index])
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            stripped.append(character)
            index += 1
            continue
        if character == "/" and index + 1 < len(contents):
            next_character = contents[index + 1]
            if next_character == "/":
                index += 2
                while index < len(contents) and contents[index] != "\n":
                    index += 1
                continue
            if next_character == "*":
                index += 2
                while index < len(contents):
                    if contents[index] == "\n":
                        stripped.append("\n")
                    if contents[index : index + 2] == "*/":
                        index += 2
                        break
                    index += 1
                continue
        stripped.append(character)
        index += 1
    return "".join(stripped)


def _operation_names(source: Path) -> set[str]:
    names: set[str] = set()
    for path in source.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if path.name.endswith((".test.ts", ".test.tsx")) or "test" in path.parts:
            continue
        contents = _strip_typescript_comments(path.read_text(encoding="utf-8"))
        for match in DOCUMENT_PATTERN.finditer(contents):
            names.update(OPERATION_PATTERN.findall(match.group("document")))
    return names


def _request(path: str, route: str | None = None) -> HttpRequest:
    request = RequestFactory().get(path)
    request.resolver_match = None if route is None else SimpleNamespace(route=route)  # type: ignore[assignment]
    return request


def test_operation_names_scans_gql_documents_and_skips_comments(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "ops.ts").write_text(
        "// query Prose is not captured\n"
        "const a = gql`query ProjektListe($page: Int!) { x }`;\n"
        "const b = gql`\n  mutation CreateProjekt { y }\n`;\n"
        'const url = "https://example.test/* no comment */";\n',
        encoding="utf-8",
    )
    (source / "ops.test.ts").write_text(
        "const c = gql`query TestOnly { z }`;", encoding="utf-8"
    )
    assert _operation_names(source) == {"ProjektListe", "CreateProjekt"}


def test_graphql_metric_allowlist_covers_frontend_source() -> None:
    frontend = _operation_names(FRONTEND_SOURCE)
    assert frontend
    assert frontend <= set(GRAPHQL_METRIC_OPERATION_ALLOWLIST)


def test_classifies_graphql_without_exposing_operation_or_path() -> None:
    assert classify_api_request(_request("/graphql/")) == ("graphql", "graphql")


@pytest.mark.parametrize(
    "query",
    ["query HealthProbe { __typename }", "\n query\tHealthProbe\r\n{\n__typename\t}\n"],
)
def test_exact_synthetic_graphql_probe_is_not_classified(query: str) -> None:
    request = RequestFactory().get(
        "/graphql/", {"query": query, "operationName": "HealthProbe"}
    )
    assert classify_api_request(request) is None


@pytest.mark.parametrize(
    ("method", "operation_name", "query"),
    [
        ("POST", "HealthProbe", "query HealthProbe { __typename }"),
        ("GET", "Other", "query HealthProbe { __typename }"),
        ("GET", "HealthProbe", "query HealthProbe { viewer { id } }"),
        ("GET", "HealthProbe", "query Other { __typename }"),
        ("GET", "HealthProbe", "query HealthProbe { __typename # comment\n}"),
    ],
)
def test_graphql_probe_lookalikes_remain_user_traffic(
    method: str, operation_name: str, query: str
) -> None:
    factory = RequestFactory()
    request = (factory.post if method == "POST" else factory.get)(
        "/graphql/", {"query": query, "operationName": operation_name}
    )
    assert classify_api_request(request) == ("graphql", "graphql")


def test_probe_tolerates_missing_query_parameters() -> None:
    from forge.observability.graphql_probe import is_synthetic_graphql_health_probe

    other_path = cast(HttpRequest, SimpleNamespace(method="GET", path_info="/health/"))
    assert is_synthetic_graphql_health_probe(other_path) is False
    without_get = cast(
        HttpRequest, SimpleNamespace(method="GET", path_info="/graphql/")
    )
    assert is_synthetic_graphql_health_probe(without_get) is False
    non_string = cast(
        HttpRequest,
        SimpleNamespace(
            method="GET", path_info="/graphql/", GET=SimpleNamespace(get=lambda _n: 3)
        ),
    )
    assert is_synthetic_graphql_health_probe(non_string) is False


def test_classifies_resolved_auth_route_by_family() -> None:
    assert classify_api_request(_request("/api/login/", "api/login/")) == (
        "auth",
        "login",
    )
    assert classify_api_request(_request("/api/logout/", "api/logout/")) == (
        "auth",
        "logout",
    )


def test_collapses_unresolved_and_unsafe_auth_paths() -> None:
    assert classify_api_request(_request("/api/user-controlled/")) == (
        "auth",
        "unmatched",
    )
    assert classify_api_request(_request("/api/x/", "other/x/")) == (
        "auth",
        "unmatched",
    )
    assert classify_api_request(_request("/api/x/", "api/<int:pk>/")) == (
        "auth",
        "other",
    )


def test_ignores_non_api_routes() -> None:
    assert classify_api_request(_request("/health/live/")) is None


def test_middleware_records_one_auth_outcome() -> None:
    request = _request("/api/login/", "api/login/")
    expected_response = HttpResponse(status=401)
    get_response = Mock(return_value=expected_response)
    with patch("forge.observability.middleware.record_api_response") as record:
        response = ApiMetricsMiddleware(get_response)(request)
    assert response is expected_response
    get_response.assert_called_once_with(request)
    record.assert_called_once()
    assert record.call_args.args == (("auth", "login"),)
    assert record.call_args.kwargs["method"] == "GET"
    assert record.call_args.kwargs["status"] == 401
    assert record.call_args.kwargs["duration_seconds"] >= 0


def test_middleware_does_not_record_health_requests() -> None:
    get_response = Mock(return_value=HttpResponse(status=200))
    with patch("forge.observability.middleware.record_api_response") as record:
        ApiMetricsMiddleware(get_response)(_request("/health/live/", "health/live/"))
    record.assert_not_called()


def test_synthetic_probe_leaves_counter_and_histogram_unchanged() -> None:
    counter_labels = {
        "api": "graphql",
        "endpoint_group": "graphql",
        "method": "GET",
        "status": "200",
    }
    histogram_labels = {k: v for k, v in counter_labels.items() if k != "status"}

    def snapshot() -> tuple[float | None, float | None]:
        return (
            REGISTRY.get_sample_value("forge_api_requests_total", counter_labels),
            REGISTRY.get_sample_value(
                "forge_api_request_duration_seconds_count", histogram_labels
            ),
        )

    before = snapshot()
    request = RequestFactory().get(
        "/graphql/",
        {"query": "query HealthProbe { __typename }", "operationName": "HealthProbe"},
    )
    ApiMetricsMiddleware(lambda _request: HttpResponse(status=200))(request)
    assert snapshot() == before


def test_real_named_graphql_query_increments_counter_once() -> None:
    labels = {
        "api": "graphql",
        "endpoint_group": "graphql",
        "method": "GET",
        "status": "200",
    }
    before = REGISTRY.get_sample_value("forge_api_requests_total", labels) or 0
    request = RequestFactory().get(
        "/graphql/", {"query": "query Me { me { username } }", "operationName": "Me"}
    )
    ApiMetricsMiddleware(lambda _request: HttpResponse(status=200))(request)
    assert REGISTRY.get_sample_value("forge_api_requests_total", labels) == before + 1


def test_middleware_awaits_async_downstream() -> None:
    request = _request("/api/login/", "api/login/")
    expected_response = HttpResponse(status=201)
    downstream = Mock()

    async def get_response(request: HttpRequest) -> HttpResponse:
        downstream(request)
        return expected_response

    middleware = ApiMetricsMiddleware(get_response)
    assert iscoroutinefunction(middleware)

    async def invoke() -> HttpResponse:
        result = await middleware(request)
        assert isinstance(result, HttpResponse)
        return result

    with patch("forge.observability.middleware.record_api_response") as record:
        response = asyncio.run(invoke())
    assert response is expected_response
    downstream.assert_called_once_with(request)
    assert record.call_args.kwargs["status"] == 201


def test_middleware_records_security_redirect_before_view() -> None:
    request = _request("/api/login/", "api/login/")
    view = Mock(return_value=HttpResponse(status=200))
    with (
        override_settings(
            ALLOWED_HOSTS=["testserver"],
            SECURE_SSL_REDIRECT=True,
            SECURE_PROXY_SSL_HEADER=None,
            SECURE_REDIRECT_EXEMPT=[],
        ),
        patch("forge.observability.middleware.record_api_response") as record,
    ):
        response = cast(
            HttpResponse,
            ApiMetricsMiddleware(cast(SyncGetResponse, SecurityMiddleware(view)))(
                request
            ),
        )
    assert response.status_code == 301
    view.assert_not_called()
    assert record.call_args.kwargs["status"] == 301


def test_api_request_duration_describes_time_to_response_headers() -> None:
    assert API_REQUEST_DURATION._documentation == (
        "Forge API time to response headers in seconds."
    )


@pytest.mark.parametrize(
    ("method", "expected"), [("propfind", "OTHER"), ("", "OTHER"), ("post", "POST")]
)
def test_record_normalizes_methods_and_clamps_duration(
    method: str, expected: str
) -> None:
    labels = {
        "api": "auth",
        "endpoint_group": "logout",
        "method": expected,
        "status": "500",
    }
    before = REGISTRY.get_sample_value("forge_api_requests_total", labels) or 0
    record_api_response(
        ("auth", "logout"), method=method, status=500, duration_seconds=-1.0
    )
    assert REGISTRY.get_sample_value("forge_api_requests_total", labels) == before + 1


@override_settings(**METRICS_HOST_SETTINGS)
@pytest.mark.django_db
def test_metrics_accepts_ip_host_from_dns_discovered_prometheus_target() -> None:
    response = Client(raise_request_exception=False).get(
        "/metrics", HTTP_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 200
    assert b"django_http_requests_total" in response.content


@override_settings(**METRICS_HOST_SETTINGS)
@pytest.mark.django_db
def test_metrics_head_accepts_ip_host_from_prometheus_target() -> None:
    response = Client(raise_request_exception=False).head(
        "/metrics", HTTP_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 200


@override_settings(**METRICS_HOST_SETTINGS)
def test_metrics_post_does_not_adapt_ip_host() -> None:
    response = Client(raise_request_exception=False).post(
        "/metrics", HTTP_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 400


@override_settings(**METRICS_HOST_SETTINGS)
def test_non_metrics_request_still_rejects_ip_host() -> None:
    response = Client(raise_request_exception=False).get(
        "/health/live/", HTTP_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 400


@override_settings(**METRICS_HOST_SETTINGS)
@pytest.mark.parametrize("path", ["/metrics/", "/metrics//"])
def test_metrics_does_not_adapt_unsupported_trailing_slashes(path: str) -> None:
    response = Client(raise_request_exception=False).get(
        path, HTTP_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 400


@override_settings(**METRICS_HOST_SETTINGS)
@pytest.mark.parametrize(
    "host", [" 172.19.0.23:8000", "172.19.0.23:99999", f"127.0.0.1:{'9' * 5000}"]
)
def test_metrics_does_not_adapt_malformed_ip_host(host: str) -> None:
    response = Client(raise_request_exception=False).get("/metrics", HTTP_HOST=host)
    assert response.status_code == 400


@override_settings(
    ALLOWED_HOSTS=["testserver", "web"],
    INTERNAL_METRICS_HOST="web",
    USE_X_FORWARDED_HOST=True,
)
def test_metrics_does_not_trust_ip_forwarded_host() -> None:
    response = Client(raise_request_exception=False).get(
        "/metrics", HTTP_HOST="testserver", HTTP_X_FORWARDED_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 400


@override_settings(ALLOWED_HOSTS=["testserver"], INTERNAL_METRICS_HOST="")
def test_metrics_without_internal_host_keeps_django_host_validation() -> None:
    response = Client(raise_request_exception=False).get(
        "/metrics", HTTP_HOST="172.19.0.23:8000"
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "host",
    ["172.19.0.23", "172.19.0.23:8000", "[2001:db8::23]", "[2001:db8::23]:8000"],
)
def test_metrics_host_parser_accepts_strict_ip_host_grammar(host: str) -> None:
    assert _is_ip_host(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "",
        " 172.19.0.23:8000",
        "172.19.0.23:0",
        "172.19.0.23:65536",
        "172.19.0.23:not-a-port",
        "172.19.0.23:8000garbage",
        "127.0.0.1.",
        "127.0.0.1.:8000",
        "172.19.0.999:8000",
        "2001:db8::23",
        "[172.19.0.23]",
        "[2001:db8::23]:",
        "[2001:db8::23]:0",
        "[2001:db8::23]:65536",
        "[2001:db8::23]:not-a-port",
        "[2001:db8::23]garbage",
        "web",
        f"127.0.0.1:{'9' * 5000}",
    ],
)
def test_metrics_host_parser_rejects_hosts_outside_strict_grammar(host: str) -> None:
    assert _is_ip_host(host) is False
