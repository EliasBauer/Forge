"""Misst Antwortstatus und Zeit bis zu den Response-Headern je API."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest
from django.http.response import HttpResponseBase

from forge.observability.api_metrics import classify_api_request, record_api_response

type SyncGetResponse = Callable[[HttpRequest], HttpResponseBase]
type AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponseBase]]


class ApiMetricsMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: SyncGetResponse | AsyncGetResponse) -> None:
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self._is_async:
            return self._acall(request)

        started = time.perf_counter()
        response = cast(SyncGetResponse, self.get_response)(request)
        self._record(request, response, started)
        return response

    async def _acall(self, request: HttpRequest) -> HttpResponseBase:
        started = time.perf_counter()
        response = await cast(AsyncGetResponse, self.get_response)(request)
        self._record(request, response, started)
        return response

    def _record(
        self,
        request: HttpRequest,
        response: HttpResponseBase,
        started: float,
    ) -> None:
        classification = classify_api_request(request)
        if classification is not None:
            record_api_response(
                classification,
                method=cast(str, request.method),
                status=response.status_code,
                duration_seconds=time.perf_counter() - started,
            )
