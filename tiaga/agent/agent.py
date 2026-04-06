from __future__ import annotations
import json
from pathlib import Path
from typing import AsyncGenerator
from client.llm_client import LLM_client
from client.response import StreamEventType, ToolCall, ToolResultMessage  # Fix typo: reaponse -> response
from tiaga.tools_manager.registry import create_default_registry
from tiaga.config.config import Config
from .events import AgentEvent, AgentEventType
from context.manager import ContextManager


class Agent:
    def __init__(self, config: Config):
        self.client = LLM_client(config)
        self.usage = None
        self.context_manager = ContextManager(config)
        self.tool_registry = create_default_registry()
        self.config = config

    async def run(self, message: str):
        yield AgentEvent.agent_start(messages=message)
        self.context_manager.add_user_message(message)
        final_response = None

        async for event in self._agentic_loop():
            yield event
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "")

        yield AgentEvent.agent_end(usage=self.usage, response=final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent]:
        max_turn = self.config.max_turns
        for turn_num in range(max_turn):

            tool_schema = self.tool_registry.get_schemas()
            response_text = ""
            tools_calls: list[ToolCall] = []

            async for event in self.client.chat_completion(
                message=self.context_manager.get_messages(),
                tools=tool_schema if tool_schema else None,
                stream=True,
            ):
                if event.type == StreamEventType.TEXT_DELTA and event.text_delta:
                    content = event.text_delta.content
                    response_text += content
                    yield AgentEvent.text_delta(content=content)

                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_call:
                        tools_calls.append(event.tool_call)

                elif event.type == StreamEventType.MESSAGE_COMPLETE:
                    self.usage = event.usage

                elif event.type == StreamEventType.ERROR:
                    yield AgentEvent.agent_error(
                        detail=None,
                        error=event.error or "Unknown error occurred.",
                    )

            assistant_tool_calls: list[dict[str, object]] = []
            for tool_call in tools_calls:
                assistant_tool_calls.append(
                    {
                        "id": tool_call.call_id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name or "",
                            "arguments": json.dumps(tool_call.arguments or {}),
                        },
                    }
                )

            if response_text or assistant_tool_calls:
                self.context_manager.add_assistant_message(
                    response_text or "",
                    tool_calls=assistant_tool_calls,
                )

            if response_text:
                yield AgentEvent.text_complete(response_text)
            
            if not tools_calls :
                return

            if tools_calls:
                tool_call_results: list[ToolResultMessage] = []

                for tool_call in tools_calls:
                    yield AgentEvent.tool_call_start(
                        call_id=tool_call.call_id,
                        name=tool_call.name,
                        arguments=tool_call.arguments,
                    )

                    result = await self.tool_registry.invoke(
                        tool_call.name,
                        tool_call.arguments,
                        self.config.cwd,
                    )

                    yield AgentEvent.tool_call_complete(
                        tool_call.call_id,
                        tool_call.name,
                        result,
                    )

                    tool_call_results.append(
                        ToolResultMessage(
                            tool_call_id=tool_call.call_id,  # Fix: was tool_call.call_id via wrong attr name
                            content=result.output,           # Fix: pass result content, not raw result object
                            is_error=not result.success,
                        )
                    )

                for tool_result in tool_call_results:
                    self.context_manager.add_tool_message(
                        tool_result.tool_call_id,   # Fix: was tool_result.call_id (wrong attribute)
                        tool_result.content,
                    )

                # Fix: recurse so the LLM can respond to tool results
                async for event in self._agentic_loop():
                    yield event

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client:
            await self.client.close_client()
            self.client = None
