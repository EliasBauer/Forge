from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin


class DisableCSRFForGraphQL(MiddlewareMixin):
    def process_request(self, request: HttpRequest) -> None:
        if request.path.startswith("/graphql"):
            setattr(request, "_dont_enforce_csrf_checks", True)  # noqa: B010
