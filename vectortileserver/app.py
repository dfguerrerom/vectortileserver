from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route

from vectortileserver.endpoints import pmtiles_endpoint


def create_app(tile_server_instance):
    """Create the Starlette application with routes and middleware."""

    async def pmtiles_wrapper(request):
        return await pmtiles_endpoint(request, tile_server_instance)

    # No shutdown route: it had no callers, and any page the user visits can
    # reach a loopback port. TileServer.stop() sets the event directly.
    routes = [
        Route("/pmtiles", pmtiles_wrapper),
    ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=tile_server_instance.config.cors_origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )
    ]

    return Starlette(debug=tile_server_instance.config.debug, routes=routes, middleware=middleware)
