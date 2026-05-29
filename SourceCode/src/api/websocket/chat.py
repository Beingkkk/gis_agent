"""Chat WebSocket handler.

Provides streaming Q&A over WebSocket using LLM's on_chunk callback.

Design:
    T-UX-04 (DC-UX-04)
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import (
    get_llm_client,
    get_prompt_builder,
    get_registry,
    get_session_manager,
)
from llm.qa import answer_question

logger = logging.getLogger(__name__)


async def handle_chat_websocket(websocket: WebSocket, session_id: str) -> None:
    """Handle a chat WebSocket connection.

    Receives JSON messages from the frontend, streams LLM responses
    back as ``{"type": "chunk", "content": "..."}`` frames,
    followed by ``{"type": "done"}``.

    Args:
        websocket: FastAPI WebSocket instance.
        session_id: Session UUID from URL path.
    """
    session_manager = get_session_manager()
    llm_client = get_llm_client()
    prompt_builder = get_prompt_builder()

    # Validate session before accepting
    session = session_manager.get_session(session_id)
    if session is None:
        await websocket.close(code=1008, reason="Invalid session")
        return

    await websocket.accept()

    loop = asyncio.get_running_loop()

    try:
        while True:
            data: dict[str, Any] = await websocket.receive_json()
            user_message = data.get("message", "")
            if not user_message:
                continue

            # Build template context from all available templates
            registry = get_registry()
            templates = registry.list_templates()

            # Stream LLM response via on_chunk callback.
            # answer_question is synchronous I/O; run it in a thread
            # pool so the event loop stays responsive.
            def _on_chunk(chunk: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({"type": "chunk", "content": chunk}),
                    loop,
                )

            await asyncio.to_thread(
                answer_question,
                user_input=user_message,
                templates=templates,
                history=list(session.history),
                client=llm_client,
                builder=prompt_builder,
                on_chunk=_on_chunk,
            )

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.debug("Chat WebSocket disconnected: %s", session_id)
    except Exception as exc:
        logger.exception("Chat WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()
        except Exception:
            pass
