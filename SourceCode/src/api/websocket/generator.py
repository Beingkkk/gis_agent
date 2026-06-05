"""Template generation WebSocket handler.

Provides streaming template generation over WebSocket using LLM's
chat_stream generator. No session_id — the generator page is independent
of the Session state machine (DC-UX-07).

Design:
    DC-0096
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import get_llm_client
from llm.template_generator import (
    generate_template_stream,
    parse_generated_response,
)

logger = logging.getLogger(__name__)

# Token budget for LLM template generation input.
# Claude supports 200K context; we reserve ~12000 for the user document.
_MAX_INPUT_TOKENS = 12000


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) // 4."""
    return max(1, len(text) // 4)


async def handle_generator_websocket(websocket: WebSocket) -> None:
    """Handle a template generation WebSocket connection.

    Receives a ``{"type": "start", "document_text": "...", "config": {...}}``
    message, streams LLM response chunks back as
    ``{"type": "chunk", "content": "..."}`` frames,
    followed by ``{"type": "done", "result": {...}}`` or
    ``{"type": "error", "message": "...", "stage": "..."}``.

    Args:
        websocket: FastAPI WebSocket instance.
    """
    llm_client = get_llm_client()
    await websocket.accept()

    try:
        data: dict[str, Any] = await websocket.receive_json()

        # Protocol validation
        if data.get("type") != "start":
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Expected message type 'start'",
                    "stage": "protocol",
                }
            )
            await websocket.close()
            return

        document_text = data.get("document_text", "").strip()
        config = data.get("config", {})

        # Input validation
        if not document_text:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "document_text is required",
                    "stage": "validation",
                }
            )
            await websocket.close()
            return

        # Token budget check
        estimated_tokens = _estimate_tokens(document_text)
        if estimated_tokens > _MAX_INPUT_TOKENS:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": (
                        f"文档过长（约 {estimated_tokens} tokens），"
                        f"请精简后重试（上限 {_MAX_INPUT_TOKENS} tokens）"
                    ),
                    "stage": "validation",
                }
            )
            await websocket.close()
            return

        # Stream generation
        loop = asyncio.get_running_loop()
        chunks: list[str] = []

        def on_chunk(chunk: str) -> None:
            chunks.append(chunk)
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "chunk", "content": chunk}),
                loop,
            )

        # Stream generation (includes internal retry on parse failure)
        try:
            full_text = await asyncio.to_thread(
                generate_template_stream,
                client=llm_client,
                document_text=document_text,
                config=config,
                on_chunk=on_chunk,
            )
            if not full_text.strip():
                logger.error("LLM returned empty response for template generation")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "LLM 返回为空，请检查输入内容或稍后重试。",
                        "stage": "generation",
                    }
                )
                await websocket.close()
                return
            parsed = parse_generated_response(full_text)
        except ValueError as exc:
            logger.error("Failed to parse generated template: %s", exc)
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"LLM 输出解析失败: {exc}",
                    "stage": "parsing",
                }
            )
            await websocket.close()
            return

        # Sanitize params and auto-complete
        from llm.template_generator import (
            assemble_j2_body,
            auto_complete_params,
            sanitize_params,
        )

        params = sanitize_params(parsed.get("params", []))
        # LLM prompt uses "command_template"; API model uses "body".
        # Also accept "id" as fallback for "template_id".
        raw_body = parsed.get("body") or parsed.get("command_template", "")
        params = auto_complete_params(raw_body, params)

        # Assemble full .j2 file content (DC-0094)
        parsed_with_params = dict(parsed)
        parsed_with_params["params"] = params
        j2_body = assemble_j2_body(parsed_with_params)

        # Send done with structured result
        await websocket.send_json(
            {
                "type": "done",
                "result": {
                    "template_id": parsed.get("template_id")
                    or parsed.get("id", "generated"),
                    "name": parsed.get("name", "Generated Template"),
                    "description": parsed.get("description", ""),
                    "body": j2_body,
                    "params": params,
                    "concepts": parsed.get("concepts", []),
                    "notes": parsed.get("notes", []),
                },
            }
        )

    except WebSocketDisconnect:
        logger.debug("Generator WebSocket disconnected by client")
    except Exception as exc:
        logger.exception("Generator WebSocket error")
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(exc),
                    "stage": "generation",
                }
            )
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
