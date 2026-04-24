"""OpenAI Provider Implementation - handles OpenAI and OpenAI-compatible APIs"""

import json
from typing import Any, AsyncGenerator, Dict, List
from openai import AsyncOpenAI

from tiaga.client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
from tiaga.client.providers.base import BaseLLMProvider, ProviderConfig


class OpenAIProvider(BaseLLMProvider):
    """OpenAI and OpenAI-compatible API provider"""

    async def initialize(self) -> None:
        """Initialize OpenAI async client"""
        self.client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    async def close(self) -> None:
        """Close the OpenAI client"""
        if self.client:
            await self.client.close()
            self.client = None

    def build_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI format"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for tool in tools
        ]

    def normalize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize messages to OpenAI format"""
        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if isinstance(content, (dict, list)):
                safe_content = json.dumps(content)
            elif content is None:
                safe_content = ""
            else:
                safe_content = str(content)

            item: Dict[str, Any] = {
                "role": role,
                "content": safe_content,
            }

            if role == "assistant" and message.get("tool_calls"):
                tool_calls: List[Dict[str, Any]] = []
                for call in message.get("tool_calls", []):
                    function_obj = call.get("function", {})
                    args = function_obj.get("arguments", "")
                    if not isinstance(args, str):
                        args = json.dumps(args)

                    tool_calls.append(
                        {
                            "id": call.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": function_obj.get("name", ""),
                                "arguments": args,
                            },
                        }
                    )
                item["tool_calls"] = tool_calls

            if role == "tool" and message.get("tool_call_id"):
                item["tool_call_id"] = message["tool_call_id"]

            normalized.append(item)
        return normalized

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute chat completion with OpenAI API"""
        if not self.client:
            await self.initialize()

        normalized_messages = self.normalize_messages(messages)
        kwargs = {
            "model": self.config.model_name,
            "messages": normalized_messages,
            "stream": stream,
        }

        if tools:
            kwargs["tools"] = self.build_tools(tools)
            kwargs["tool_choice"] = "auto"

        # Retry logic
        for attempt in range(3):
            try:
                if stream:
                    async for event in self._stream_response(kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(kwargs)
                    yield event
                return
            except Exception as e:
                if attempt < 2:
                    import asyncio
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=str(e),
                    )
                    return

    async def _stream_response(
        self, kwargs: Dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        """Handle streaming response from OpenAI"""
        response = await self.client.chat.completions.create(**kwargs)
        finish_reason: str | None = None
        usage: TokenUsage | None = None
        tool_calls: Dict[int, Dict[str, Any]] = {}

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=getattr(chunk.usage, "cached_tokens", None),
                )

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    text_delta=TextDelta(content=delta.content),
                )

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name or "" if tc.function else "",
                            "arguments": "",
                        }
                        if tc.function and tc.function.name:
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tc.function.name,
                                ),
                            )

                    if tc.function and tc.function.arguments:
                        tool_calls[idx]["arguments"] += tc.function.arguments
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_DELTA,
                            tool_call_delta=ToolCallDelta(
                                call_id=tool_calls[idx]["id"],
                                name=tool_calls[idx]["name"],
                                arguments_delta=tc.function.arguments,
                            ),
                        )

        for idx, tc in tool_calls.items():
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(
                    call_id=tc["id"],
                    name=tc["name"],
                    arguments=json.loads(tc["arguments"]),
                ),
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finished_reason=finish_reason,
            usage=usage,
        )

    async def _non_stream_response(
        self, kwargs: Dict[str, Any]
    ) -> StreamEvent:
        """Handle non-streaming response from OpenAI"""
        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        text_delta = None
        usage = None

        if message.content:
            text_delta = TextDelta(message.content)

        tool_calls: List[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=tc.id,
                        name=tc.function.name,
                        arguments=parse_tool_call_arguments(tc.function.arguments),
                    )
                )

        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=getattr(response.usage, "cached_tokens", None),
            )

        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            finished_reason=choice.finish_reason,
            usage=usage,
        )

    def get_capabilities(self) -> Dict[str, Any]:
        """Get OpenAI provider capabilities"""
        return {
            "supports_streaming": True,
            "supports_tool_calls": True,
            "supports_vision": True,
            "supports_parallel_tools": True,
        }

    def validate_temperature(self, temperature: float) -> float:
        """Validate temperature for OpenAI (0.0 - 2.0)"""
        return max(0.0, min(2.0, temperature))
