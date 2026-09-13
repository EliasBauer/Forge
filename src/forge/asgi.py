import os
from typing import Any, cast

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "forge.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

# Muss vor dem Import des Consumers laufen (App-Registry, GraphQL-Schema).
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.urls import re_path  # noqa: E402
from general_manager.api.graphql_subscription_consumer import (  # noqa: E402
    GraphQLSubscriptionConsumer,
)

# django-stubs typisiert re_path fuer HTTP-Views; hier ist es ein ASGI-Consumer.
_subscription_consumer = cast(Any, GraphQLSubscriptionConsumer.as_asgi())

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter([re_path(r"^graphql/?$", _subscription_consumer)])
        ),
    }
)
