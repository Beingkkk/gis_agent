"""GIS Agent API module.

HTTP + WebSocket adapter layer for the browser UI.
Provides FastAPI application factory and dependency injection.

Public API:
    create_app() -> FastAPI

Design:
    T-UX-01 (DC-UX-01, DC-UX-03)
"""

from api.main import create_app

__all__ = ["create_app"]
