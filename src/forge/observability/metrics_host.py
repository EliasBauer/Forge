"""Erlaubt Prometheus, /metrics ueber die Replikat-IP zu scrapen (DNS-SD)."""

from __future__ import annotations

from ipaddress import ip_address

from django.conf import settings
from django.http import HttpRequest
from django.http.request import split_domain_port
from django.utils.deprecation import MiddlewareMixin


def _is_ip_host(value: str) -> bool:
    if not value.startswith("["):
        raw_domain, separator, _port = value.rpartition(":")
        raw_domain = raw_domain if separator else value
        if raw_domain.endswith("."):
            return False

    domain, port = split_domain_port(value)
    if not domain:
        return False
    if port:
        if len(port) > 5 or not port.isascii() or not port.isdecimal():
            return False
        if not 0 < int(port) <= 65535:
            return False

    bracketed = domain.startswith("[") and domain.endswith("]")
    address = domain[1:-1] if bracketed else domain

    try:
        version = ip_address(address).version
    except ValueError:
        return False
    return version == (6 if bracketed else 4)


class InternalMetricsHostMiddleware(MiddlewareMixin):
    """Adapt only direct Prometheus IP targets to an allowed internal host.

    Prometheus DNS service discovery connects to each replica IP and therefore
    sends that IP in the Host header. Django must keep rejecting such hosts on
    every normal route; the metrics endpoint is the sole exception.
    """

    def process_request(self, request: HttpRequest) -> None:
        if request.method not in {"GET", "HEAD"}:
            return
        if request.path_info != "/metrics":
            return

        internal_host = getattr(settings, "INTERNAL_METRICS_HOST", "")
        if not internal_host or internal_host not in settings.ALLOWED_HOSTS:
            return

        if _is_ip_host(request.META.get("HTTP_HOST", "")):
            request.META["HTTP_HOST"] = internal_host
