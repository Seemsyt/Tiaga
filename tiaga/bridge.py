#!/usr/bin/env python3
"""
Single-request stdio bridge for the Ink CLI frontend.

Request protocol:
  {"action": "list_sessions"}
  {"action": "get_history", "thread_id": "..."}
  {"action": "chat", "thread_id": "...", "message": "..."}

Response protocol:
  - Non-streaming actions emit a single JSON line.
  - Chat actions emit a stream of JSON events ending with {"type": "done"}.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from .chat_engine import ChatEngine


def emit(event: dict[str, Any]) -> None:
    print(json.dumps(event), flush=True)


def _message_to_dict(message: HumanMessage | AIMessage) -> dict[str, str]:
    role = "assistant" if isinstance(message, AIMessage) else "user"
    content = message.content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        text = "\n".join(part for part in parts if part)
    else:
        text = str(content)
    return {"role": role, "content": text}


async def handle_list_sessions(engine: ChatEngine) -> None:
    sessions = await engine.list_sessions()
    emit({
        "type": "session_list",
        "sessions": [{"id": session} for session in sessions],
    })


async def handle_history(engine: ChatEngine, request: dict[str, Any]) -> None:
    thread_id = str(request.get("thread_id", "")).strip()
    if not thread_id:
        emit({"type": "error", "error": "Missing thread_id"})
        return

    db_path = Path(engine.db_path)
    if not db_path.exists() or db_path.stat().st_size == 0:
        emit({"type": "history", "thread_id": thread_id, "messages": []})
        return

    messages = await engine.get_visible_history(thread_id)
    visible = [
        _message_to_dict(message)
        for message in messages
        if isinstance(message, (HumanMessage, AIMessage))
    ]
    emit({"type": "history", "thread_id": thread_id, "messages": visible})


async def handle_chat(engine: ChatEngine, request: dict[str, Any]) -> None:
    message = str(request.get("message", "")).strip()
    thread_id = str(request.get("thread_id", "")).strip() or "session"

    if not message:
        emit({"type": "error", "error": "Empty message"})
        return

    try:
        async for event in engine.stream_turn(message, thread_id):
            kind = event.get("event")

            if kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                input_preview = ""
                if isinstance(tool_input, dict):
                    first_val = next(iter(tool_input.values()), "")
                    input_preview = str(first_val)[:80] if first_val else ""
                emit({
                    "type": "tool_start",
                    "name": tool_name,
                    "inputPreview": input_preview,
                })
                continue

            if kind == "on_tool_end":
                output = event.get("data", {}).get("output", "")
                result_preview = str(output).replace("\n", " ")[:120]
                if len(str(output)) > 120:
                    result_preview += "..."
                emit({"type": "tool_end", "resultPreview": result_preview})
                continue

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and getattr(chunk, "content", None):
                    content = chunk.content
                    if content:
                        emit({"type": "text_delta", "delta": content})

        emit({"type": "done"})
    except Exception as exc:
        emit({"type": "error", "error": str(exc)})


async def main() -> None:
    line = sys.stdin.readline()
    if not line:
        return

    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        emit({"type": "error", "error": f"Invalid JSON: {exc}"})
        return

    engine = ChatEngine()
    action = request.get("action")

    if action == "list_sessions":
        await handle_list_sessions(engine)
        return

    if action == "get_history":
        await handle_history(engine, request)
        return

    if action == "chat":
        await handle_chat(engine, request)
        return

    emit({"type": "error", "error": f"Unknown action: {action}"})


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
