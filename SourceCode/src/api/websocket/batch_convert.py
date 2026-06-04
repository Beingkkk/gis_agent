"""Batch convert WebSocket handler.

Provides streaming batch script conversion over WebSocket.
Receives script + template metadata, streams LLM response back as chunks.

Design:
    plan-batch-convert v1.0.0 (DC-0113), CODE-5
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import get_llm_client, get_registry
from llm.batch_convert import BATCH_SYSTEM_PROMPT, build_batch_convert_prompt
from llm.models import Message

logger = logging.getLogger(__name__)


async def handle_batch_convert_websocket(
    websocket: WebSocket, session_id: str
) -> None:
    """Handle batch convert WebSocket connection.

    Receives JSON request with script, template_id, and params.
    Streams LLM response back as ``{"type": "chunk", "content": "..."}``
    frames, followed by ``{"type": "done"}``.

    Args:
        websocket: FastAPI WebSocket instance.
        session_id: Session UUID from URL path (validated but not used for
            state lookup since batch convert is stateless).
    """
    await websocket.accept()
    loop = asyncio.get_running_loop()

    try:
        data: dict[str, Any] = await websocket.receive_json()
        script = data.get("script", "")
        template_id = data.get("template_id", "")
        params = data.get("params", {})

        if not script or not template_id:
            await websocket.send_json(
                {"type": "error", "message": "Missing script or template_id"}
            )
            await websocket.close()
            return

        registry = get_registry()
        template = registry.get_template(template_id)
        if template is None:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Template not found: {template_id}",
                }
            )
            await websocket.close()
            return

        params_meta = [
            {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
                "default": p.default,
            }
            for p in template.params
        ]

        user_prompt = build_batch_convert_prompt(
            script, template.name, params_meta, params
        )
        llm_client = get_llm_client()

        # Run LLM stream in a background thread so the event loop stays
        # responsive. Use run_coroutine_threadsafe to push chunks back.
        def _run_stream() -> str:
            chunks: list[str] = []
            for chunk in llm_client.chat_stream(
                system_prompt=BATCH_SYSTEM_PROMPT,
                messages=[Message(role="user", content=user_prompt)],
                temperature=0.2,
            ):
                chunks.append(chunk)
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json(
                        {"type": "chunk", "content": chunk}
                    ),
                    loop,
                )
            return "".join(chunks)

        await asyncio.to_thread(_run_stream)
        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.debug("Batch convert WebSocket disconnected: %s", session_id)
    except Exception as exc:
        logger.exception("Batch convert WebSocket error: %s", exc)
        try:
            await websocket.send_json(
                {"type": "error", "message": str(exc)}
            )
            await websocket.close()
        except Exception:
            pass
