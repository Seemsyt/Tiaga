#!/usr/bin/env python3
"""
Stdio bridge for Ink CLI frontend.

Protocol (JSON lines):
  stdin -> {"message": "...", "thread_id": "..."}
  stdout -> {"type": "...", ...}

Event types:
  text_start, text_delta, tool_start, tool_end, done, error, permission_request
"""

import json
import sys
import asyncio
from typing import Any, Dict

# Add tiaga module to path
sys.path.insert(0, '/home/seems/tiaga')

from tiaga.chat_engine import ChatEngine


def emit(event: Dict[str, Any]) -> None:
    """Emit a JSON event to stdout."""
    print(json.dumps(event), flush=True)


async def main() -> None:
    """Main loop: read stdin lines, process, emit events."""
    engine = ChatEngine()
    thread_id = "session"
    permission_cache: Dict[str, bool] = {}

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                message = request.get("message", "").strip()
                thread_id = request.get("thread_id", thread_id)

                if not message:
                    emit({"type": "error", "error": "Empty message"})
                    continue

                emit({"type": "text_start"})

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
                            "inputPreview": input_preview
                        })
                        # Request permission
                        emit({"type": "permission_request", "name": tool_name})
                        # Wait for permission response
                        try:
                            resp_line = sys.stdin.readline()
                            if resp_line:
                                resp = json.loads(resp_line)
                                if resp.get("permission") == "approved":
                                    # Tool will execute - we'll get on_tool_end later
                                    pass
                                else:
                                    # For now just skip - proper implementation would abort
                                    emit({"type": "tool_end", "resultPreview": "[skipped]"})
                        except Exception:
                            pass
                        continue

                    if kind == "on_tool_end":
                        output = event.get("data", {}).get("output", "")
                        result_preview = str(output).replace("\n", " ")[:120]
                        if len(str(output)) > 120:
                            result_preview += "…"
                        emit({
                            "type": "tool_end",
                            "resultPreview": result_preview
                        })
                        continue

                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and getattr(chunk, "content", None):
                            content = chunk.content
                            if content:
                                emit({"type": "text_delta", "delta": content})
                        continue

                emit({"type": "done"})

            except json.JSONDecodeError as e:
                emit({"type": "error", "error": f"Invalid JSON: {e}"})
            except Exception as e:
                emit({"type": "error", "error": str(e)})

    except (EOFError, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
