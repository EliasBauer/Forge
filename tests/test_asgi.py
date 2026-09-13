import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from forge.asgi import application


@pytest.mark.django_db
def test_graphql_websocket_route_accepts_graphql_transport_ws() -> None:
    async def connect() -> tuple[bool, str | None]:
        communicator = WebsocketCommunicator(
            application, "/graphql/", subprotocols=["graphql-transport-ws"]
        )
        connected, subprotocol = await communicator.connect()
        await communicator.disconnect()
        return connected, subprotocol

    connected, subprotocol = async_to_sync(connect)()
    assert connected is True
    assert subprotocol == "graphql-transport-ws"
