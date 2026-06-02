"""FastAPI application factory.

Design:
    T-UX-01 (DC-UX-01)
"""

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def _init_dependencies() -> None:
    """Initialize core business logic dependencies.

    Wires together config, workspace, template registry, validator,
    template engine, and LLM components — mirroring CLI initialization.

    Design: DC-UX-01, DC-UX-03
    """
    from pathlib import Path

    from api.dependencies import (
        set_llm_client,
        set_prompt_builder,
        set_registry,
        set_template_engine,
        set_validator,
    )
    from core import ParamValidator, TemplateRegistry
    from llm import LLMClient, PromptBuilder
    from templates import TemplateEngine, scan_templates

    # 1. Load configuration
    try:
        from config import load_config
        load_config()
    except Exception:
        logger.warning("Config load failed, using defaults for API init")

    # 2. Scan templates and build registry
    template_dir = Path(__file__).parent.parent.parent / "data" / "templates"
    templates = scan_templates(template_dir)
    registry = TemplateRegistry(templates, template_dir)

    # 3. Build core components
    validator = ParamValidator()
    template_engine = TemplateEngine(template_dir)
    llm_client = LLMClient()
    prompt_builder = PromptBuilder()

    # 4. Register singletons for dependency injection
    set_registry(registry)
    set_validator(validator)
    set_template_engine(template_engine)
    set_llm_client(llm_client)
    set_prompt_builder(prompt_builder)

    logger.info(
        "API dependencies initialized: %d templates",
        len(templates),
    )


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI instance.

    Design:
        DC-UX-01
    """
    app = FastAPI(title="GIS Agent API")

    import os

    # Electron loads frontend from file:// or custom protocol in production,
    # so allow all origins when running under Electron (ELECTRON_MODE=1).
    # Dev browser mode still only allows Vite dev server.
    if os.environ.get("ELECTRON_MODE") == "1":
        allow_origins = ["*"]
    else:
        allow_origins = ["http://localhost:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize core dependencies before registering routes
    _init_dependencies()

    # Register routes
    from api.routes import exec_env as exec_env_routes
    from api.routes import generator as generator_routes
    from api.routes import pipeline as pipeline_routes
    from api.routes import session as session_routes
    from api.routes import templates as templates_routes
    from api.websocket.chat import handle_chat_websocket
    from api.websocket.execute import handle_execute_websocket

    app.include_router(session_routes.router, prefix="/api")
    app.include_router(templates_routes.router, prefix="/api")
    app.include_router(pipeline_routes.router, prefix="/api")
    app.include_router(generator_routes.router, prefix="/api")
    app.include_router(exec_env_routes.router, prefix="/api")

    @app.websocket("/ws/chat/{session_id}")
    async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
        """Chat WebSocket endpoint for streaming Q&A."""
        await handle_chat_websocket(websocket, session_id)

    @app.websocket("/ws/execute/{session_id}")
    async def execute_websocket(websocket: WebSocket, session_id: str) -> None:
        """Execute WebSocket endpoint for real-time script execution logs."""
        await handle_execute_websocket(websocket, session_id)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    return app


def main() -> int:
    """Entry point for `python -m api`."""
    import uvicorn

    uvicorn.run("api.main:create_app", factory=True, host="127.0.0.1", port=18000)
    return 0
