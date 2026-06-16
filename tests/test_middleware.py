"""Tests für die CSRF-Middleware."""

from unittest.mock import MagicMock

from forge.middleware import DisableCSRFForGraphQL


class TestDisableCSRFForGraphQL:
    def _make_request(self, path: str) -> MagicMock:
        request = MagicMock()
        request.path = path
        return request

    def test_graphql_path_setzt_csrf_check_flag(self) -> None:
        middleware = DisableCSRFForGraphQL(get_response=MagicMock())
        request = self._make_request("/graphql/")
        middleware.process_request(request)
        assert getattr(request, "_dont_enforce_csrf_checks", False) is True

    def test_anderer_pfad_setzt_kein_flag(self) -> None:
        middleware = DisableCSRFForGraphQL(get_response=MagicMock())
        # spec auf bekannte Attribute beschränken, damit hasattr korrekt funktioniert
        request = MagicMock(spec=["path"])
        request.path = "/admin/"
        middleware.process_request(request)
        assert not hasattr(request, "_dont_enforce_csrf_checks")
